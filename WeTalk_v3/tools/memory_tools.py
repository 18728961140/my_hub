"""
长期记忆工具（深度倾诉节点可调用的工具之一）

两套记忆的区别：
  短期记忆（checkpointer / SqliteSaver）—— 记住"这次对话聊了什么"，
    同一 thread_id 连续对话有效，换会话（thread_id）就清空。
  长期记忆（store / SqliteStore）—— 记住"这个用户是谁、经历了什么"，
    按 user_id 隔离，跨会话、重启服务都还在。

设计说明：
  记忆的"读取"不做成工具，而是在 deep_talk 节点直接把记忆拼进提示词（更可靠）；
  记忆的"保存"做成工具，让大模型倾诉过程中可以主动存，
  同时 remember 节点还会在倾诉结束后自动兜底存一次。
"""

from datetime import datetime
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore
from langgraph.store.sqlite import SqliteStore


@tool
def save_memory(
    category: Annotated[str, "记忆分类，如：背景、情绪、经历、偏好"],
    content: Annotated[str, "要记住的用户信息内容"],
    config: RunnableConfig,                         # 由 LangGraph 自动注入
    store: Annotated[SqliteStore, InjectedStore()],  # 由 LangGraph 自动注入
) -> str:
    """将用户的重要信息（姓名、经历、情绪状态等）保存到长期记忆，供以后的对话使用

    参数里的 config 和 store 不需要大模型传值，LangGraph 会自动注入：
      - config：拿到 user_id（是谁说的），用于数据隔离
      - store ：长期记忆仓库的实例（InjectedStore 表示"自动注入"）
    """
    user_id = config["configurable"].get("user_id", "anonymous")

    # store.put：写入一条记忆
    #   namespace=(user_id, "memory") -> 按用户隔离的命名空间
    #   key=category                  -> 同类信息存同一个 key（新值覆盖旧值）
    #   value=字典                    -> 记忆内容 + 时间戳
    store.put(
        namespace=(user_id, "memory"),
        key=category,
        value={
            "content": content,
            "timestamp": datetime.now().isoformat(),
        },
    )

    # 返回值会作为 ToolMessage 给大模型看，让它知道保存成功
    return f"已记住：用户 {user_id} 的 [{category}] 信息为「{content}」"
