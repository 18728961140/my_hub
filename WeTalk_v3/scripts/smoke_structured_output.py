"""结构化输出通道冒烟测试：function_calling vs json_mode

目的：验证当前模型（qwen3.8-27b，DashScope 兼容接口）在 LangChain
with_structured_output 下两种通道是否可用、解析是否稳定，
用于决定调用层是否可以从"文本 + 容错解析"升级为原生结构化输出。

用法（在项目根目录执行）：
    python scripts/smoke_structured_output.py

脚本会调用真实模型，约十几次请求；结果只打印解析成功/失败与耗时，
不打印密钥。
"""

import time
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

# 保证从任何目录执行时都能 import 到项目根目录的模块（graph/、models/）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graph.nodes import Intent, MemoryExtract
from models.llm import qwen_llm


def _classify_messages(text: str):
    """和 classify_node 一致的提示，但显式声明输出格式，方便两种通道公平对比"""
    return [
        SystemMessage(
            content=(
                "你是一个心理咨询陪伴系统的状态判断器。"
                '只输出一个 JSON 对象，例如 {"intent": "倾诉"}，'
                "intent 只能是：闲聊、倾诉、危机、求助。"
                "禁止输出数组、禁止 ```json 代码块、不要任何解释。"
            )
        ),
        HumanMessage(content=text),
    ]


def _memory_messages(text: str):
    """和 remember_node 一致的提示，声明输出 JSON 对象"""
    return [
        SystemMessage(
            content=(
                "你是心理咨询系统的记忆提取器，把值得长期记住的信息"
                '输出成 JSON 对象 {"items": [{"category": "...", "content": "..."}]}，'
                "category 取值：背景、情绪、经历、偏好。没有则输出空列表。"
                "禁止 ```json 代码块、不要任何解释。"
            )
        ),
        HumanMessage(content=text),
    ]


# (标签, 目标 schema, 消息)
CASES = [
    ("classify-倾诉", Intent, _classify_messages("我最近总是失眠，心里堵得慌，想找人说说话")),
    ("classify-求助", Intent, _classify_messages("请问焦虑发作的时候有什么缓解方法？")),
    ("classify-闲聊", Intent, _classify_messages("今天天气不错，你吃了吗？")),
    ("classify-危机", Intent, _classify_messages("活着太累了，我想结束这一切")),
    ("memory-正常", MemoryExtract, _memory_messages("我今年25岁，是一名程序员，最近在准备考研，压力很大")),
    ("memory-无信息", MemoryExtract, _memory_messages("好的谢谢")),
]

METHODS = ["function_calling", "json_mode"]


def main():
    print(f"模型：{qwen_llm.model_name}")
    results = {method: {"ok": 0, "fail": 0} for method in METHODS}
    for label, schema, messages in CASES:
        for method in METHODS:
            start = time.perf_counter()
            try:
                chain = qwen_llm.with_structured_output(
                    schema, method=method, include_raw=True
                )
                raw_result = chain.invoke(messages)
                parsed = raw_result.get("parsed")
                error = raw_result.get("parsing_error")
            except Exception as exc:  # 通道本身不支持 / 请求报错
                elapsed = time.perf_counter() - start
                print(f"[FAIL] {label:14s} {method:16s} 调用异常：{type(exc).__name__}: {exc}（{elapsed:.1f}s）")
                results[method]["fail"] += 1
                continue
            elapsed = time.perf_counter() - start
            if parsed is not None:
                results[method]["ok"] += 1
                print(f"[OK  ] {label:14s} {method:16s} -> {parsed.model_dump()}（{elapsed:.1f}s）")
            else:
                results[method]["fail"] += 1
                raw = raw_result.get("raw")
                content = getattr(raw, "content", "") if raw is not None else ""
                print(f"[FAIL] {label:14s} {method:16s} 解析失败：{error} content={content[:120]!r}（{elapsed:.1f}s）")
    print("\n汇总：", results)


if __name__ == "__main__":
    main()
