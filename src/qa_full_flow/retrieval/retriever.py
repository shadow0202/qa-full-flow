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
                 reranker: Optional[Reranker] = None,
                 auto_load_bm25: bool = True):
        """
        初始化检索器

        Args:
            embedder: Embedding 模型
            vector_store: 向量数据库
            reranker: 重排序器（可选）
            auto_load_bm25: 是否自动加载 BM25 索引（默认 True）
        """
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker

        # 混合检索器
        self.hybrid_retriever = HybridRetriever(embedder, vector_store)

        # 自动加载 BM25 索引
        if auto_load_bm25:
            self._init_bm25_index()

    def _init_bm25_index(self):
        """
        初始化 BM25 索引：尝试从文件加载，如果失败则从向量库重建
        """
        # 1. 尝试从文件加载
        if self.hybrid_retriever.load_bm25_index():
            logger.info("✅ BM25 索引已从文件加载")
            self._sync_bm25_with_vector_store()
            return

        # 2. 加载失败，尝试从向量库重建
        logger.info("🔄 正在从向量库重建 BM25 索引...")
        try:
            all_docs = self._get_all_docs_from_vector_store()
            if all_docs:
                self.build_bm25_index(all_docs)
                # 保存索引
                self.hybrid_retriever.save_bm25_index()
                logger.info(f"✅ BM25 索引已从向量库重建并保存（{len(all_docs)} 个文档）")
            else:
                logger.info("ℹ️  向量库中无文档，BM25 索引将在首次入库时构建")
        except Exception as e:
            logger.warning(f"⚠️  BM25 索引重建失败: {e}", exc_info=True)
    
    def _sync_bm25_with_vector_store(self):
        """
        同步 BM25 索引与向量库：检查文档数量是否一致，不一致则重建
        """
        try:
            current_count = self.vector_store.count()
            bm25_count = len(self.hybrid_retriever.bm25_doc_ids)
            
            if current_count != bm25_count:
                logger.info(f"🔄 BM25 索引文档数 ({bm25_count}) 与向量库 ({current_count}) 不一致，正在重建...")
                all_docs = self._get_all_docs_from_vector_store()
                if all_docs:
                    self.build_bm25_index(all_docs)
                    self.hybrid_retriever.save_bm25_index()
                    logger.info(f"✅ BM25 索引已重建（{len(all_docs)} 个文档）")
        except Exception as e:
            logger.warning(f"⚠️  BM25 索引同步失败: {e}", exc_info=True)

    def _get_all_docs_from_vector_store(self) -> list:
        """
        从向量库获取所有文档

        Returns:
            文档列表，每个包含 "doc_id", "content", "metadata"
        """
        try:
            all_docs = self.vector_store.get()
            if not all_docs.get("ids"):
                return []

            return [
                {
                    "doc_id": doc_id,
                    "content": content,
                    "metadata": metadata
                }
                for doc_id, content, metadata in zip(
                    all_docs["ids"],
                    all_docs["documents"],
                    all_docs["metadatas"]
                )
            ]
        except Exception as e:
            logger.warning(f"⚠️  从向量库获取文档失败: {e}", exc_info=True)
            return []

    def search(self, query: str,
               n_results: int = 5,
               filters: Optional[Dict] = None,
               include_distances: bool = True,
               use_hybrid: bool = True,
               use_reranker: bool = True,
               top_k_for_rerank: int = 20,
               bm25_query: Optional[str] = None,
               metadata_query: Optional[str] = None) -> List[Dict]:
        """
        语义检索

        Args:
            query: 查询文本（默认用于向量检索）
            n_results: 返回结果数
            filters: 过滤条件 {"module": "订单支付", "source_type": "test_case"}
            include_distances: 是否包含距离
            use_hybrid: 是否使用混合检索（默认 True）
            use_reranker: 是否使用重排序（默认 True）
            top_k_for_rerank: 重排序候选数
            bm25_query: BM25 检索专用 query（默认使用 query）
            metadata_query: 元数据检索专用 query（默认使用 query）

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
                    filters=filters,
                    bm25_query=bm25_query,
                    metadata_query=metadata_query
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

    def save_bm25_index(self) -> bool:
        """
        保存 BM25 索引到文件

        Returns:
            是否保存成功
        """
        return self.hybrid_retriever.save_bm25_index()

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
            logger.warning(f"获取文档失败: {e}")

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
