"""
图编排模块（LangGraph 的"地图"）

nodes.py 定义了"做什么"（节点函数），
本文件决定"怎么连、怎么走"（节点、边、分支、结束）：

图结构：
  START -> classify（聊天状态判断）
             ├─(闲聊)   -> small_talk -> END
             ├─(危机)   -> crisis_respond -> END
             ├─(求助)   -> consult_talk -> END
             └─(倾诉)   -> crisis_check（危机二次检测）
                            ├─(高危)   -> crisis_respond -> END
                            └─(正常)   -> deep_talk
                                           ├─(有工具调用且未超限) -> tools -> deep_talk（循环）
                                           ├─(回答完毕/超限)      -> reflect（质量自评）
                                           │                        ├─(不合格且未重试) -> deep_talk（重答）
                                           │                        └─(通过)          -> remember -> END

另外在这里初始化两套记忆：
  短期记忆 checkpointer（SqliteSaver）：每个节点执行完自动存档，支持多轮对话
  长期记忆 store（SqliteStore）       ：跨会话记住用户信息
"""

import sqlite3
from pathlib import Path

from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.sqlite import SqliteStore

from graph.nodes import (
    classify_node,
    consult_talk_node,
    crisis_check_node,
    crisis_respond_node,
    deep_talk_node,
    deep_talk_tools,
    reflect_node,
    remember_node,
    small_talk_node,
)
from graph.state import ChatState
from utils.config import checkpoint_db_path, store_db_path


MAX_TOOL_ROUNDS = 2  # deep_talk 最多允许的工具调用轮次（防止死循环）


def route_after_deep_talk(state: ChatState) -> str:
    """deep_talk 之后的路由：
    - 有工具调用且未超限  -> tools（去执行工具）
    - 有工具调用但已超限  -> reflect（强制结束，防止死循环）
    - 回答完毕（无工具调用）-> reflect（先做质量自评）
    """
    last = state["messages"][-1] if state["messages"] else None
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        if state.get("tool_rounds", 0) < MAX_TOOL_ROUNDS:
            return "tools"
        return "reflect"
    return "reflect"


def route_after_crisis_check(state: ChatState) -> str:
    """危机检测之后的路由：高危 -> crisis_respond；正常 -> deep_talk"""
    # 注意：条件边路由函数必须返回"路由表里的键"（high/normal），
    # 而不是目标节点名；节点名由路由表的值来指定。
    return "high" if state.get("risk_level") == "high" else "normal"


def route_after_reflect(state: ChatState) -> str:
    """反思之后的路由：需要重答 -> deep_talk；通过 -> remember"""
    return "deep_talk" if state.get("reflect_pending") else "remember"


def _ensure_dir(path: str) -> None:
    """确保数据库文件所在目录存在（首次运行还没有 data/ 目录）"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def build_chat_graph():
    """构建并编译整张聊天图"""
    _ensure_dir(checkpoint_db_path)
    _ensure_dir(store_db_path)

    # ============ 短期记忆：SqliteSaver（checkpointer） ============
    # checkpointer 会在每个节点执行前后自动"存档"，相当于给对话做快照。
    # 同一个 thread_id 再次调用时，自动恢复历史状态 -> 多轮对话有记忆。
    # check_same_thread=False：允许不同线程共用连接（FastAPI 多线程需要）
    # isolation_level=None：关闭 sqlite 自动事务，避免和 LangGraph 内部事务冲突
    saver = SqliteSaver(
        conn=sqlite3.connect(checkpoint_db_path, check_same_thread=False, isolation_level=None)
    )
    saver.setup()  # 创建所需的表

    # ============ 长期记忆：SqliteStore ============
    # store 是跨会话的"仓库"，按 (user_id, "memory") 命名空间隔离数据。
    # 节点函数和工具可以通过注入的 store 参数读写它。
    store = SqliteStore(
        conn=sqlite3.connect(store_db_path, check_same_thread=False, isolation_level=None)
    )
    store.setup()

    # ============ 搭图 ============
    # StateGraph(ChatState)：声明状态类型，图中所有节点共享这个状态
    builder = StateGraph(ChatState)

    # 注册节点：给每个函数起一个名字（图中用名字来连线）
    builder.add_node("classify", classify_node)             # 聊天状态判断（闲聊/倾诉/危机/求助）
    builder.add_node("crisis_check", crisis_check_node)     # 危机二次检测（关键词 + LLM）
    builder.add_node("crisis_respond", crisis_respond_node) # 危机干预（安抚 + 热线）
    builder.add_node("consult_talk", consult_talk_node)     # 知识问答（求助类）
    builder.add_node("small_talk", small_talk_node)         # 闲聊
    builder.add_node("deep_talk", deep_talk_node)           # 深度倾诉（可调工具）
    builder.add_node("tools", ToolNode(deep_talk_tools))    # 工具执行器
    builder.add_node("reflect", reflect_node)               # 回答质量自评
    builder.add_node("remember", remember_node)             # 记忆提取

    # START 是图的固定入口：先进状态判断节点
    builder.add_edge(START, "classify")

    # 条件边：根据 classify 写入的 intent 字段决定走哪条路
    #   第二个参数是"路由函数"：读状态，返回一个 key
    #   第三个参数是"路由表"：key -> 去哪个节点
    builder.add_conditional_edges(
        "classify",
        lambda state: state.get("intent", "闲聊"),
        {"闲聊": "small_talk", "倾诉": "crisis_check", "危机": "crisis_respond", "求助": "consult_talk"},
    )

    # 闲聊 / 知识问答 / 危机干预 回答完，直接到图的出口 END
    builder.add_edge("small_talk", END)
    builder.add_edge("consult_talk", END)
    builder.add_edge("crisis_respond", END)

    # 倾诉路径先做危机二次检测：高危走危机干预，正常才进深度倾诉
    builder.add_conditional_edges(
        "crisis_check",
        route_after_crisis_check,
        {"high": "crisis_respond", "normal": "deep_talk"},
    )

    # 深度倾诉的条件边：自定义路由，检查最后一条消息有没有 tool_calls，
    # 并叠加"工具轮次上限"保护（防止死循环）
    builder.add_conditional_edges(
        "deep_talk",
        route_after_deep_talk,
        {"tools": "tools", "reflect": "reflect"},
    )

    # 工具执行完，结果会以 ToolMessage 追加进消息历史，再回到 deep_talk 让模型继续
    builder.add_edge("tools", "deep_talk")

    # 反思节点：不合格回 deep_talk 重答，通过才去 remember
    builder.add_conditional_edges(
        "reflect",
        route_after_reflect,
        {"deep_talk": "deep_talk", "remember": "remember"},
    )

    # 记忆提取完成，整个流程结束
    builder.add_edge("remember", END)

    # compile：把图编译成可执行对象，并挂上记忆组件
    return builder.compile(checkpointer=saver, store=store)


# 模块加载时构建全局唯一的图（服务启动时创建一次，接口复用同一个实例）
chat_graph = build_chat_graph()
