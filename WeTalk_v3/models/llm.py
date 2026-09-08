"""
大模型配置模块

作用：创建全局唯一的大模型对象，供所有节点和工具复用。

这里用的是通义千问（DashScope），它提供 OpenAI 兼容接口，
所以直接用 LangChain 的 ChatOpenAI 连接即可。
"""

from langchain_openai import ChatOpenAI

from utils.config import qwen_model_name, qwen_api_key, qwen_base_url

# ChatOpenAI：LangChain 对 OpenAI 风格接口的封装（模型名/密钥/地址/温度）
qwen_llm = ChatOpenAI(
    model=qwen_model_name,   # 模型名称
    api_key=qwen_api_key,    # 密钥
    base_url=qwen_base_url,  # 接口地址
    temperature=0.3,         # 温度：越低越严谨，越高越发散（0~1）
)
