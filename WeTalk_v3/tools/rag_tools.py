"""
RAG 检索工具（深度倾诉节点可调用的工具之一）

工具（Tool）是 LangChain 里"让大模型使用外部能力"的标准方式：
  - 用 @tool 装饰器把一个普通函数变成工具
  - 工具的名称、描述、参数说明会自动注册给大模型
  - 大模型判断"需要查知识库"时，就会发起对这个工具的调用，
    工具执行完，结果作为 ToolMessage 返回给大模型
"""

from typing import Annotated

from langchain_core.tools import tool

from retriever.bm25_retriever import retrieve


@tool
def retrieve_knowledge(query: Annotated[str, "用户倾诉的核心内容或问题"]) -> str:
    """
    根据用户的倾诉内容或问题，从本地心理咨询知识库中检索相关知识点。

    Args:
        query: str，必填，用户倾诉的核心内容或问题

    Returns:
        str，检索到的相关文档片段文本
    """
    # Annotated[str, "描述"]：给参数加中文说明，大模型能理解该传什么
    docs = retrieve(query)  # 调 BM25 检索
    if not docs:
        return "知识库中没有找到相关内容"
    # 把多段文档用空行拼成一段"参考资料"文本，方便大模型阅读
    return "\n\n".join(doc.page_content for doc in docs)
