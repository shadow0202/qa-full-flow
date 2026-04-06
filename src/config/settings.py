import os
from pathlib import Path
from typing import Optional


class Settings:
    """统一配置管理"""
    
    def __init__(self):
        # 项目根目录
        self.ROOT_DIR = Path(__file__).parent.parent.parent
        
        # 数据目录
        self.DATA_DIR = self.ROOT_DIR / "data"
        self.RAW_DATA_DIR = self.DATA_DIR / "raw"
        self.VECTOR_DB_DIR = self.DATA_DIR / "vector_db"
        
        # 创建目录
        self.VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
        self.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Embedding模型配置
        self.EMBEDDING_MODEL = os.getenv(
            "EMBEDDING_MODEL",
            "BAAI/bge-m3"
        )
        self.EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")

        # Reranker模型配置
        self.RERANKER_MODEL = os.getenv(
            "RERANKER_MODEL",
            "BAAI/bge-reranker-large"
        )
        self.RERANKER_DEVICE = os.getenv("RERANKER_DEVICE", "cpu")

        # ChromaDB配置
        self.CHROMA_PATH = os.getenv(
            "CHROMA_PATH",
            str(self.VECTOR_DB_DIR / "chroma_kb")
        )
        self.CHROMA_COLLECTION_NAME = os.getenv(
            "CHROMA_COLLECTION_NAME",
            "test_knowledge"
        )
        
        # LLM配置（用于Agent）
        self.LLM_API_KEY = os.getenv("LLM_API_KEY", "")
        self.LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        
        # JIRA配置
        self.JIRA_URL = os.getenv("JIRA_URL", "https://your-company.atlassian.net")
        self.JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
        self.JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
        self.JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "")  # 为空则拉取所有项目
        
        # Confluence配置
        self.CONFLUENCE_URL = os.getenv("CONFLUENCE_URL", "https://your-company.atlassian.net/wiki")
        self.CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL", "")
        self.CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN", "")
        
        # API服务配置
        self.API_HOST = os.getenv("API_HOST", "0.0.0.0")
        self.API_PORT = int(os.getenv("API_PORT", "8000"))
        
        # HF镜像（国内加速）
        if os.getenv("HF_ENDPOINT"):
            os.environ["HF_ENDPOINT"] = os.getenv("HF_ENDPOINT")
        else:
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


# 全局配置实例
settings = Settings()
