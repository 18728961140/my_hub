"""
配置模块（所有"参数"的集中地）

作用：统一从 .env 文件读取配置，其他模块从这里拿值，
避免每个文件都自己读环境变量、各写各的。
"""

import os

from dotenv import load_dotenv

# 把 .env 文件里的变量加载进环境（比如 QWEN_API_KEY 这种密钥）
load_dotenv()

# ============== 大模型配置 ==============
# os.getenv("名字")：读取环境变量；读取不到返回 None
qwen_model_name = os.getenv("QWEN_MODEL_NAME")  # 千问模型名，如 qwen-plus
qwen_api_key = os.getenv("QWEN_API_KEY")        # API 密钥
qwen_base_url = os.getenv("QWEN_BASE_URL")      # OpenAI 兼容接口地址

# ============== 知识库配置 ==============
# 本地心理咨询知识文档所在目录（放 .md / .txt 文件，启动后自动建 BM25 索引）
knowledge_dir = os.getenv("KNOWLEDGE_DIR", "knowledge")

# ============== 记忆存储配置 ==============
# 短期记忆（对话检查点）和长期记忆（用户记忆）的 SQLite 数据库文件路径
# getenv 第二个参数是默认值：没配置就用 "data"
db_dir = os.getenv("DB_DIR", "data")
checkpoint_db_path = os.path.join(db_dir, "checkpoint.sqlite")  # 短期记忆库（多轮对话）
store_db_path = os.path.join(db_dir, "store.sqlite")            # 长期记忆库（跨会话）
