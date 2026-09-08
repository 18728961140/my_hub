"""
API 路由模块：把 LangGraph 工作流暴露成 HTTP 接口

整个链路：
  前端 POST /api/chat/ask
    -> FastAPI 收到请求
    -> 调用 chat_graph（LangGraph 工作流：状态判断 -> 闲聊/深度倾诉 -> 记忆）
    -> 把 AI 生成的文字流式推给前端（边生成边发，不用等全部完成）
"""

import asyncio

from fastapi import APIRouter
from langchain_core.messages import AIMessageChunk, HumanMessage
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from graph.chat_graph import chat_graph

# 创建子路由：prefix="/chat"，最后在 main.py 挂到 /api 下 => 完整地址 /api/chat/ask
chat_router = APIRouter(prefix="/chat")


class ChatRequest(BaseModel):
    """前端发来的请求体（Pydantic 自动做格式校验，并转成对象）"""

    question: str = Field(..., description="用户发言")
    thread_id: str = Field(default="default", description="会话 ID（短期记忆隔离）")
    user_id: str = Field(default="anonymous", description="用户 ID（长期记忆隔离）")


async def _generator(req: ChatRequest):
    """异步生成器：一点一点地产出回答文字（流式响应的核心）

    为什么用"后台线程 + 队列"？
    - chat_graph 用的是同步版 SqliteSaver，不支持异步方法；
    - 所以把同步的 stream 循环扔进线程池（asyncio.to_thread）跑，
      生成的文字通过 asyncio.Queue 传给异步生成器，再发给前端。
    """
    # config 里的 thread_id / user_id 会贯穿整个工作流：
    #   thread_id -> 短期记忆（同一会话连续对话）
    #   user_id   -> 长期记忆（跨会话记住用户）
    config = {"configurable": {"thread_id": req.thread_id, "user_id": req.user_id}}

    queue: asyncio.Queue = asyncio.Queue()  # 线程 -> 生成器的"传送带"
    error: Exception | None = None          # 线程里出错时传回主协程

    def run():
        """后台线程：跑完整的 LangGraph 工作流，把生成的字送入队列"""
        nonlocal error
        try:
            for message_chunk, metadata in chat_graph.stream(
                {"messages": [HumanMessage(content=req.question)]},  # 用户问题包成消息喂给图
                config=config,
                stream_mode="messages",  # 流式模式：每生成一个文字片段就吐出来
            ):
                # 只保留"最终回答节点"的文字（闲聊/深度倾诉/知识问答/危机干预），
                # 过滤掉分类、记忆提取等内部节点的结构化 JSON 输出
                node = metadata.get("langgraph_node")
                if (
                    node in ("small_talk", "deep_talk", "consult_talk", "crisis_respond")
                    and isinstance(message_chunk, AIMessageChunk)
                    and message_chunk.content
                ):
                    queue.put_nowait(message_chunk.content)
        except Exception as exc:  # noqa: BLE001
            error = exc
        finally:
            queue.put_nowait(None)  # None 表示"流结束"信号

    # 启动后台线程任务
    asyncio.create_task(asyncio.to_thread(run))

    # 主协程：从队列取文字片段，一个接一个 yield 给 HTTP 流
    while True:
        chunk = await queue.get()
        if chunk is None:          # 收到结束信号
            if error:
                raise error        # 把线程里的错误抛给 FastAPI（返回 500）
            break
        yield chunk


@chat_router.post("/ask")
async def ask(req: ChatRequest):
    """聊天接口：返回 text/event-stream（SSE）流式响应"""
    return StreamingResponse(
        _generator(req),
        media_type="text/event-stream",
    )
