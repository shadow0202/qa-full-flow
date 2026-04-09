"""检索器 - 语义检索功能（支持混合检索 + 重排序）"""
import logging
from typing import List, Dict, Optional
from src.qa_full_flow.embedding.embedder import Embedder
from src.qa_full_flow.vector_store.chroma_store import ChromaStore
from src.qa_full_flow.retrieval.hybrid import HybridRetriever
from src.qa_full_flow.retrieval.reranker import Reranker

logger = logging.getLogger(__name__)


class Retriever:
    """知识库检索器（支持多种检索策略）"""

    def __init__(self, embedder: Embedder, vector_store: ChromaStore,
                 reranker: Optional[Reranker] = None):
        """
        初始化检索器

        Args:
            embedder: Embedding 模型
            vector_store: 向量数据库
            reranker: 重排序器（可选）
        """
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker

        # 混合检索器
        self.hybrid_retriever = HybridRetriever(embedder, vector_store)

    def search(self, query: str,
               n_results: int = 5,
               filters: Optional[Dict] = None,
               include_distances: bool = True,
               use_hybrid: bool = True,
               use_reranker: bool = True,
               top_k_for_rerank: int = 20) -> List[Dict]:
        """
        语义检索

        Args:
            query: 查询文本
            n_results: 返回结果数
            filters: 过滤条件 {"module": "订单支付", "source_type": "test_case"}
            include_distances: 是否包含距离
            use_hybrid: 是否使用混合检索（默认 True）
            use_reranker: 是否使用重排序（默认 True）
            top_k_for_rerank: 重排序候选数

        Returns:
            检索结果列表
        """
        # 1. 检索
        try:
            if use_hybrid:
                # 混合检索：多路召回 + RRF 融合
                results = self.hybrid_retriever.search(
                    query=query,
                    n_results=top_k_for_rerank if use_reranker else n_results,
                    top_k_for_rerank=top_k_for_rerank,
                    filters=filters
                )
            else:
                # 纯向量检索
                results = self._vector_search(query, n_results, filters, include_distances)
        except Exception as e:
            logger.error(f"❌ 检索失败: {e}")
            return []

        # 2. 重排序
        if use_reranker and self.reranker and len(results) > 0:
            try:
                results = self.reranker.rerank(
                    query=query,
                    documents=results,
                    top_k=n_results
                )
            except Exception as e:
                logger.warning(f"⚠️  重排序失败: {e}，返回原始结果")

        return results

    def _vector_search(self, query: str, n_results: int,
                       filters: Optional[Dict] = None,
                       include_distances: bool = True) -> List[Dict]:
        """纯向量检索（兼容旧接口）"""
        query_embedding = self.embedder.encode_single(query, normalize=True)

        query_params = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
        }

        if filters:
            query_params["where"] = filters

        if include_distances:
            query_params["include"] = ["documents", "metadatas", "distances"]
        else:
            query_params["include"] = ["documents", "metadatas"]

        results = self.vector_store.query(**query_params)
        return self._format_results(results)

    def build_bm25_index(self, documents: List[Dict]):
        """
        构建 BM25 索引（用于混合检索）

        Args:
            documents: 文档列表，每个包含 "doc_id", "content", "metadata"
        """
        self.hybrid_retriever.build_bm25_index(documents)

    def search_by_id(self, doc_id: str) -> Optional[Dict]:
        """
        根据ID获取文档

        Args:
            doc_id: 文档ID

        Returns:
            文档信息或None
        """
        try:
            result = self.vector_store.get(ids=[doc_id])
            if result.get("documents"):
                return {
                    "doc_id": result["ids"][0],
                    "content": result["documents"][0],
                    "metadata": result["metadatas"][0]
                }
        except Exception as e:
            print(f"⚠️  获取文档失败: {e}")

        return None

    def get_collection_info(self) -> Dict:
        """获取知识库信息"""
        return self.vector_store.get_collection_info()

    def _format_results(self, results: Dict) -> List[Dict]:
        """格式化检索结果"""
        formatted = []

        if not results["documents"][0]:
            return formatted

        for i, (doc, metadata) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0]
        )):
            item = {
                "rank": i + 1,
                "content": doc,
                "metadata": metadata
            }

            if "distances" in results:
                item["distance"] = results["distances"][0][i]
                # 计算相似度（余弦距离转相似度）
                item["similarity"] = 1 - results["distances"][0][i]

            formatted.append(item)

        return formatted
