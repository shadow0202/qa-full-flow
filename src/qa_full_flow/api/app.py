"""FastAPI应用工厂

使用模块化路由和中间件。
服务实例通过依赖注入动态创建，无需全局变量。
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.qa_full_flow.core.config import settings
from src.qa_full_flow.core.logging import setup_logging
from src.qa_full_flow.api.routes.health import router as health_router
from src.qa_full_flow.api.routes.knowledge import router as knowledge_router
from src.qa_full_flow.api.routes.testcases import router as testcases_router
from src.qa_full_flow.api.routes.prompt_management import router as prompt_router
from src.qa_full_flow.api.middleware.logging import LoggingMiddleware
from src.qa_full_flow.api.middleware.error_handler import register_exception_handlers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动日志（使用 logger 替代 print）
    logger.info("\n" + "=" * 50)
    logger.info(f"🚀 正在启动 {settings.APP_NAME} v{settings.APP_VERSION}...")
    logger.info("=" * 50)

    # 初始化日志系统
    setup_logging(
        level="DEBUG" if settings.DEBUG else "INFO",
        log_file=settings.LOG_FILE,
        use_json=settings.LOG_USE_JSON,
    )

    # 注意：服务实例（Embedder, VectorStore, Retriever 等）
    # 不再在此处初始化，而是通过 dependencies.py 按需创建。
    # 这样避免了全局变量污染，也便于单元测试。

    # 构建 BM25 索引（如果需要，可在首个请求时懒加载）
    logger.info("ℹ️  BM25 索引将在首次检索请求时懒加载构建")

    # 检查 LLM 配置
    try:
        from src.qa_full_flow.agent.llm_service import LLMService
        llm = LLMService()
        if llm.is_available():
            logger.info("🤖 LLM服务可用，启用AI测试用例生成")
        else:
            logger.info("⚠️  LLM服务未配置，使用简单模板模式")
    except Exception as e:
        logger.warning(f"⚠️  LLM服务检查失败: {e}")

    logger.info("\n✅ 系统初始化完成，准备就绪！\n")

    yield

    # 关闭
    logger.info("\n👋 系统关闭")


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
    app.include_router(prompt_router)  # Prompt 模板管理

    return app
