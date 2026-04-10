"""健康检查路由"""
from fastapi import APIRouter
from src.qa_full_flow.core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION
    }
