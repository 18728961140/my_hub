"""
BM25 检索模块（深度倾诉的"找资料"环节）

BM25 是一种经典的"关键词匹配"检索算法，思路是：
  1. 把文档和问题都切成词（中文用 jieba 分词）
  2. 统计每个词在文档里出现的频率（出现越多越相关）
  3. 同时惩罚"所有文档都有的常见词"（如"的""了"，没有区分度）
  4. 按相关度打分排序，返回最相关的前 k 段

它和向量检索（语义匹配）不同：BM25 只做字面匹配，不"理解"语义。
但对心理咨询这类知识点文档来说，简单、快速、效果够用。
"""

from pathlib import Path

import jieba
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils.config import knowledge_dir

# 全局缓存检索器：第一次构建后复用，避免每次请求都重新分词、建索引
_retriever: BM25Retriever | None = None


def _load_documents() -> list[Document]:
    """加载 knowledge 目录下的所有 .md/.txt 文档，并按段落切成小块。

    为什么切块？整篇文档太长，检索应该返回"最相关的那一小段"，
    而不是把整本书塞给大模型。
    """
    root = Path(knowledge_dir)
    if not root.exists():
        raise FileNotFoundError(f"知识库目录不存在: {root.resolve()}")

    # RecursiveCharacterTextSplitter：递归式文本分割器
    # 优先按 \n\n（段落）切，再按 \n、句号切，尽量不从句子中间断开
    # chunk_size=300：每块约 300 字
    # chunk_overlap=50：相邻块重叠 50 字，防止一个知识点被从中间切断
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "？"],
    )

    docs: list[Document] = []
    for file_path in sorted(root.glob("*.md")) + sorted(root.glob("*.txt")):
        text = file_path.read_text(encoding="utf-8")
        for i, chunk in enumerate(splitter.split_text(text)):
            if chunk.strip():
                docs.append(
                    Document(
                        page_content=chunk.strip(),
                        metadata={"source": file_path.name, "chunk": i},
                    )
                )
    return docs


def build_index() -> BM25Retriever:
    """创建 BM25 检索器。

    preprocess_func=jieba.lcut：指定中文分词器。
    中文没有天然空格分词，必须先用 jieba 切成词，BM25 才能做词频统计。
    k=5：每次检索返回最相关的 5 段。
    """
    global _retriever
    docs = _load_documents()
    _retriever = BM25Retriever.from_documents(
        documents=docs,
        k=5,
        preprocess_func=jieba.lcut,
    )
    return _retriever


def get_retriever() -> BM25Retriever:
    """获取检索器（懒加载：第一次调用时才真正构建索引）"""
    global _retriever
    if _retriever is None:
        build_index()
    return _retriever


def retrieve(query: str, k: int = 5) -> list[Document]:
    """对外提供的检索入口：输入问题，返回最相关的文档片段列表"""
    if not query.strip():
        return []
    return get_retriever().invoke(query)[:k]


if __name__ == "__main__":
    # 直接运行本文件可测试检索效果：python -m retriever.bm25_retriever
    retriever = build_index()
    print(f"知识库文档片段数: {len(_load_documents())}")
    for doc in retriever.invoke("我最近很焦虑，睡不着怎么办"):
        print("-" * 40)
        print(doc.page_content)
