"""依赖注入"""
from functools import lru_cache
from typing import Optional

from src.config import settings as app_settings


def get_settings():
    """获取配置"""
    return get_settings_cached()


@lru_cache()
def get_settings_cached():
    """获取配置（缓存）"""
    return app_settings


def get_session_manager():
    """获取会话管理器"""
    from src.agent.test_session import session_manager
    return session_manager


def get_retriever():
    """获取检索器"""
    from src.retrieval.retriever import Retriever
    from src.embedding.embedder import Embedder
    from src.vector_store.chroma_store import ChromaStore

    embedder = Embedder()
    vector_store = ChromaStore()
    return Retriever(embedder, vector_store)


def get_llm_service():
    """获取LLM服务"""
    from src.agent.llm_service import LLMService
    return LLMService()
