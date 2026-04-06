"""健康检查路由"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "AI测试用例与知识库系统",
        "version": "0.2.0"
    }
