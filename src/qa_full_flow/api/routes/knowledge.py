"""知识库API路由"""
from fastapi import APIRouter, HTTPException

from src.config import settings
from src.api.schemas import (
    IngestRequest, IngestResponse,
    SearchRequest, SearchResponse, SearchResult,
    CollectionInfoResponse
)
from src.retrieval.retriever import Retriever
from src.embedding.embedder import Embedder
from src.vector_store.chroma_store import ChromaStore
from src.data_pipeline.pipeline import DataPipeline
from src.data_pipeline.loaders.jsonl_loader import JSONLLoader

router = APIRouter(prefix="/api/v1")


def _get_retriever() -> Retriever:
    """获取检索器实例"""
    embedder = Embedder()
    vector_store = ChromaStore()
    return Retriever(embedder, vector_store)


def _get_pipeline() -> DataPipeline:
    """获取数据流水线实例"""
    embedder = Embedder()
    vector_store = ChromaStore()
    return DataPipeline(embedder, vector_store)


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(request: SearchRequest):
    """知识库检索接口"""
    try:
        retriever = _get_retriever()
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
async def ingest_data(request: IngestRequest):
    """数据入库接口"""
    try:
        loader = JSONLLoader()
        pipeline = _get_pipeline()
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
