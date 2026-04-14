"""依赖注入

提供FastAPI依赖注入函数，替代全局变量。
使用 lru_cache 实现实例缓存，避免重复创建。
"""
import logging
from functools import lru_cache
from typing import Optional

from src.qa_full_flow.core.config import settings as app_settings

logger = logging.getLogger(__name__)


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


@lru_cache(maxsize=2)
def get_embedder():
    """获取Embedding服务（实例缓存）"""
    from src.qa_full_flow.embedding.embedder import Embedder
    return Embedder()


@lru_cache(maxsize=2)
def get_vector_store():
    """获取向量存储（实例缓存）"""
    from src.qa_full_flow.vector_store.chroma_store import ChromaStore
    return ChromaStore()


@lru_cache(maxsize=2)
def get_reranker():
    """获取重排序器（实例缓存，加载失败返回None）"""
    try:
        from src.qa_full_flow.retrieval.reranker import Reranker
        reranker = Reranker()
        logger.info("✅ Reranker已初始化")
        return reranker
    except Exception as e:
        logger.warning(f"⚠️  Reranker模型加载失败: {e}，将跳过重排序")
        return None


@lru_cache(maxsize=2)
def get_retriever():
    """获取检索器（实例缓存）"""
    from src.qa_full_flow.retrieval.retriever import Retriever

    embedder = get_embedder()
    vector_store = get_vector_store()
    reranker = get_reranker()  # 注入Reranker实例
    return Retriever(embedder, vector_store, reranker=reranker)


@lru_cache(maxsize=2)
def get_pipeline():
    """获取数据管道（实例缓存）"""
    from src.qa_full_flow.data_pipeline.pipeline import DataPipeline
    from src.qa_full_flow.data_pipeline.chunker import RecursiveCharacterSplitter

    embedder = get_embedder()
    vector_store = get_vector_store()
    
    # 初始化文档切分器
    chunker = RecursiveCharacterSplitter(
        chunk_size=800,
        chunk_overlap=100
    )
    
    return DataPipeline(embedder, vector_store, chunker=chunker)


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


@lru_cache(maxsize=1)
def get_tapd_loader():
    """获取TAPD加载器"""
    try:
        from src.qa_full_flow.data_pipeline.loaders.tapd_loader import TapdLoader
        from src.qa_full_flow.core.config import settings

        if settings.TAPD_API_USER and settings.TAPD_API_PASSWORD and settings.TAPD_WORKSPACE_ID:
            return TapdLoader(
                workspace_id=settings.TAPD_WORKSPACE_ID,
                api_user=settings.TAPD_API_USER,
                api_password=settings.TAPD_API_PASSWORD,
                verify_ssl=True
            )
        return None
    except Exception as e:
        logger.exception(f"获取 TapdLoader 失败: {e}")
        return None
