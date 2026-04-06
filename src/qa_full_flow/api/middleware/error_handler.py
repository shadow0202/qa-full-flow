"""全局错误处理中间件"""
import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP异常处理"""
    logger.error(
        f"HTTP error: {exc.status_code} - {exc.detail} "
        f"path={request.url.path} method={request.method}"
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """通用异常处理"""
    logger.error(
        f"Unexpected error: {str(exc)} "
        f"path={request.url.path} method={request.method}",
        exc_info=True
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "内部服务器错误",
            "status_code": 500
        }
    )


def register_exception_handlers(app):
    """注册异常处理器到应用"""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
