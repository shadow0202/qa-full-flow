"""依赖注入

提供FastAPI依赖注入函数，替代全局变量。
"""
from functools import lru_cache
from typing import Optional

from src.qa_full_flow.core.config import settings as app_settings


def get_settings():
    """获取配置"""
    return get_settings_cached()


@lru_cache()
def get_settings_cached():
    """获取配置（缓存）"""
    return app_settings


def get_session_manager():
    """获取会话管理器"""
    from src.qa_full_flow.agent.test_session import session_manager
    return session_manager


def get_embedder():
    """获取Embedding服务"""
    from src.qa_full_flow.embedding.embedder import Embedder
    return Embedder()


def get_vector_store():
    """获取向量存储"""
    from src.qa_full_flow.vector_store.chroma_store import ChromaStore
    return ChromaStore()


def get_retriever():
    """获取检索器"""
    from src.qa_full_flow.retrieval.retriever import Retriever
    
    embedder = get_embedder()
    vector_store = get_vector_store()
    return Retriever(embedder, vector_store)


def get_pipeline():
    """获取数据管道"""
    from src.qa_full_flow.data_pipeline.pipeline import DataPipeline
    
    embedder = get_embedder()
    vector_store = get_vector_store()
    return DataPipeline(embedder, vector_store)


def get_llm_service():
    """获取LLM服务"""
    from src.qa_full_flow.agent.llm_service import LLMService
    return LLMService()


def get_test_agent():
    """获取测试Agent
    
    注意：TestAgent 类当前未实现，此依赖项暂不可用。
    如需使用旧版 API (/testcase/generate)，请先实现 TestAgent 类。
    """
    # TODO: 实现 TestAgent 类或移除此依赖
    from fastapi import HTTPException
    raise HTTPException(
        status_code=503,
        detail="TestAgent 尚未实现，请使用分阶段 API (/testcase/session/*)"
    )


def get_confluence_loader():
    """获取Confluence加载器"""
    try:
        from src.qa_full_flow.data_pipeline.loaders.confluence_loader import ConfluenceLoader
        from src.qa_full_flow.core.config import settings

        if settings.CONFLUENCE_URL and settings.CONFLUENCE_EMAIL and settings.CONFLUENCE_API_TOKEN:
            return ConfluenceLoader(
                url=settings.CONFLUENCE_URL,
                email=settings.CONFLUENCE_EMAIL,
                api_token=settings.CONFLUENCE_API_TOKEN,
                verify_ssl=True
            )
        return None
    except Exception:
        return None
