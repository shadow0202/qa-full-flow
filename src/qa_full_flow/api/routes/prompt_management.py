"""Prompt 模板管理 API

提供 Prompt 模板的查询、更新、版本管理功能。
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.qa_full_flow.agent.prompt_manager import get_prompt_manager, PromptTemplate

router = APIRouter(prefix="/api/v1/prompts", tags=["Prompt管理"])


class PromptInfo(BaseModel):
    """Prompt 基本信息"""
    name: str
    version: str
    description: str = ""
    variables: List[str] = []


class PromptDetail(BaseModel):
    """Prompt 详细信息"""
    name: str
    version: str
    content: str
    description: str = ""
    variables: List[str] = []
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = {}


class PromptUpdateRequest(BaseModel):
    """更新 Prompt 请求"""
    name: str = Field(..., description="Prompt 名称")
    version: str = Field(..., description="版本号")
    content: str = Field(..., description="模板内容")
    description: str = Field("", description="描述")
    variables: Optional[List[str]] = Field(None, description="变量列表")


class PromptListResponse(BaseModel):
    """Prompt 列表响应"""
    success: bool
    prompts: List[PromptInfo]
    total: int


class PromptDetailResponse(BaseModel):
    """Prompt 详情响应"""
    success: bool
    prompt: PromptDetail


class PromptUpdateResponse(BaseModel):
    """Prompt 更新响应"""
    success: bool
    message: str
    prompt: PromptDetail


@router.get("/list", response_model=PromptListResponse)
async def list_prompts():
    """
    列出所有 Prompt 模板

    返回所有已加载的 Prompt 模板基本信息。
    """
    try:
        manager = get_prompt_manager()
        prompts = manager.list_prompts()

        return PromptListResponse(
            success=True,
            prompts=[PromptInfo(**p) for p in prompts],
            total=len(prompts)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 Prompt 列表失败: {str(e)}")


@router.get("/{name}/versions", response_model=PromptListResponse)
async def list_prompt_versions(name: str):
    """
    列出指定 Prompt 的所有版本

    Args:
        name: Prompt 名称
    """
    try:
        manager = get_prompt_manager()
        all_prompts = manager.list_prompts()

        # 过滤指定名称的版本
        versions = [p for p in all_prompts if p["name"] == name]

        return PromptListResponse(
            success=True,
            prompts=[PromptInfo(**p) for p in versions],
            total=len(versions)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取版本列表失败: {str(e)}")


@router.get("/{name}/{version}", response_model=PromptDetailResponse)
async def get_prompt(name: str, version: str):
    """
    获取指定版本的 Prompt 模板详情

    Args:
        name: Prompt 名称
        version: 版本号
    """
    try:
        manager = get_prompt_manager()
        template = manager.get(name, version)

        return PromptDetailResponse(
            success=True,
            prompt=PromptDetail(
                name=template.name,
                version=template.version,
                content=template.content,
                description=template.description,
                variables=template.variables,
                created_at=template.created_at,
                updated_at=template.updated_at,
                metadata=template.metadata,
            )
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Prompt 模板不存在: {name}:{version}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 Prompt 详情失败: {str(e)}")


@router.post("/reload")
async def reload_prompts():
    """
    重新加载所有 Prompt 模板

    用于在修改模板文件后手动触发重新加载（如果未启用热重载）。
    """
    try:
        manager = get_prompt_manager()
        manager.reload()

        return {
            "success": True,
            "message": f"Prompt 模板已重新加载，共 {len(manager._templates)} 个",
            "total": len(manager._templates)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新加载 Prompt 失败: {str(e)}")


@router.get("/{name}/latest", response_model=PromptDetailResponse)
async def get_latest_prompt(name: str):
    """
    获取 Prompt 的最新版本

    Args:
        name: Prompt 名称
    """
    try:
        manager = get_prompt_manager()
        template = manager._get_latest_version(name)

        if not template:
            raise HTTPException(status_code=404, detail=f"Prompt 模板不存在: {name}")

        return PromptDetailResponse(
            success=True,
            prompt=PromptDetail(
                name=template.name,
                version=template.version,
                content=template.content,
                description=template.description,
                variables=template.variables,
                created_at=template.created_at,
                updated_at=template.updated_at,
                metadata=template.metadata,
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取最新 Prompt 失败: {str(e)}")
