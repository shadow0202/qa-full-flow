"""知识库API路由"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Annotated

from src.qa_full_flow.core.config import settings
from src.qa_full_flow.api.schemas import (
    IngestRequest, IngestResponse,
    SearchRequest, SearchResponse, SearchResult,
    CollectionInfoResponse
)
from src.qa_full_flow.api.dependencies import get_retriever, get_pipeline
from src.qa_full_flow.retrieval.retriever import Retriever
from src.qa_full_flow.data_pipeline.pipeline import DataPipeline
from src.qa_full_flow.data_pipeline.loaders.jsonl_loader import JSONLLoader

router = APIRouter(prefix="/api/v1")


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(
    request: SearchRequest,
    retriever: Annotated[Retriever, Depends(get_retriever)]
):
    """知识库检索接口"""
    try:
        results = retriever.search(
            query=request.query,
            n_results=request.n_results,
            filters=request.filters
        )

        formatted_results = [
            SearchResult(
                rank=r["rank"],
                content=r["content"],
                metadata=r["metadata"],
                similarity=r.get("similarity")
            )
            for r in results
        ]

        return SearchResponse(
            success=True,
            query=request.query,
            results=formatted_results,
            total=len(results)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索失败: {str(e)}")


@router.post("/ingest", response_model=IngestResponse)
async def ingest_data(
    request: IngestRequest,
    pipeline: Annotated[DataPipeline, Depends(get_pipeline)]
):
    """数据入库接口"""
    try:
        loader = JSONLLoader()
        stats = pipeline.ingest(
            loader=loader,
            source=request.source_path,
            skip_existing=request.skip_existing
        )

        return IngestResponse(
            success=True,
            message="数据入库完成",
            stats=stats
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"入库失败: {str(e)}")


@router.get("/collection/info", response_model=CollectionInfoResponse)
async def get_collection_info():
    """获取知识库信息"""
    try:
        retriever = _get_retriever()
        info = retriever.get_collection_info()
        return CollectionInfoResponse(
            success=True,
            info=info
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取信息失败: {str(e)}")
