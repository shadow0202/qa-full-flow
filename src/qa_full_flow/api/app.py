"""FastAPI应用工厂

使用模块化路由和中间件。
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.qa_full_flow.core.config import settings
from src.qa_full_flow.core.logging import setup_logging
from src.qa_full_flow.api.routes.health import router as health_router
from src.qa_full_flow.api.routes.knowledge import router as knowledge_router
from src.qa_full_flow.api.routes.testcases import router as testcases_router
from src.qa_full_flow.api.middleware.logging import LoggingMiddleware
from src.qa_full_flow.api.middleware.error_handler import register_exception_handlers

# 全局服务实例（在lifespan中初始化）
embedder = None
vector_store = None
retriever = None
pipeline = None
test_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global embedder, vector_store, retriever, pipeline, test_agent

    # 启动
    setup_logging(level="DEBUG" if settings.DEBUG else "INFO")

    print("\n" + "=" * 50)
    print(f"🚀 正在启动 {settings.APP_NAME} v{settings.APP_VERSION}...")
    print("=" * 50)

    # 初始化Embedding和VectorStore
    from src.qa_full_flow.embedding.embedder import Embedder
    from src.qa_full_flow.vector_store.chroma_store import ChromaStore
    from src.qa_full_flow.retrieval.retriever import Retriever
    from src.qa_full_flow.data_pipeline.pipeline import DataPipeline

    embedder = Embedder()
    vector_store = ChromaStore()
    retriever = Retriever(embedder, vector_store)
    pipeline = DataPipeline(embedder, vector_store)

    # 初始化Agent
    try:
        from src.qa_full_flow.agent.test_session import session_manager
        from src.qa_full_flow.agent.llm_service import LLMService

        llm = LLMService()
        if llm.is_available():
            print("🤖 LLM服务可用，启用AI测试用例生成")
        else:
            print("⚠️  LLM服务未配置，使用简单模板模式")

        test_agent = True  # 标记可用
    except Exception as e:
        print(f"⚠️  Agent初始化失败: {e}，将使用基础功能")

    print("\n✅ 系统初始化完成，准备就绪！\n")

    yield

    # 关闭
    print("\n👋 系统关闭")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title=settings.APP_NAME,
        description="基于向量知识库的智能测试用例生成与检索系统",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # 注册中间件
    app.add_middleware(LoggingMiddleware)

    # 注册异常处理
    register_exception_handlers(app)

    # 注册路由
    app.include_router(health_router)
    app.include_router(knowledge_router)
    app.include_router(testcases_router)

    return app
