"""知识库API路由"""
import logging
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

logger = logging.getLogger(__name__)
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
    pipeline: Annotated[DataPipeline, Depends(get_pipeline)],
    retriever: Annotated[Retriever, Depends(get_retriever)]
):
    """数据入库接口"""
    try:
        loader = JSONLLoader()
        stats = pipeline.ingest(
            loader=loader,
            source=request.source_path,
            skip_existing=request.skip_existing,
            update_mode=request.update_mode
        )

        # 入库完成后重建 BM25 索引（使用统一方法）
        if stats.get("ingested", 0) > 0 or request.update_mode == "force":
            logger.info("🔄 正在重建 BM25 索引...")
            doc_count = pipeline.rebuild_bm25_index(retriever)
            if doc_count > 0:
                logger.info(f"✅ BM25 索引已重建并保存，共 {doc_count} 个文档")
        else:
            logger.info("ℹ️  无新文档，跳过 BM25 索引重建")

        return IngestResponse(
            success=True,
            message="数据入库完成",
            stats=stats
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"入库失败: {str(e)}")


@router.get("/collection/info", response_model=CollectionInfoResponse)
async def get_collection_info(
    retriever: Annotated[Retriever, Depends(get_retriever)]
):
    """获取知识库信息"""
    try:
        info = retriever.get_collection_info()
        return CollectionInfoResponse(
            success=True,
            info=info
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取信息失败: {str(e)}")
