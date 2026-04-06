"""混合检索器 - 多路召回 + RRF 融合"""
import jieba
from typing import List, Dict, Optional
from rank_bm25 import BM25Okapi
from src.vector_store.chroma_store import ChromaStore
from src.embedding.embedder import Embedder


class HybridRetriever:
    """
    混合检索器

    多路召回策略：
    1. 向量语义路：SentenceTransformer + ChromaDB
    2. BM25关键词路：jieba分词 + BM25
    3. 元数据匹配路：标题、标签精确匹配

    使用 RRF (Reciprocal Rank Fusion) 融合多路结果
    """

    def __init__(self, embedder: Embedder, vector_store: ChromaStore):
        """
        初始化混合检索器

        Args:
            embedder: Embedding 模型
            vector_store: 向量数据库
        """
        self.embedder = embedder
        self.vector_store = vector_store

        # BM25 索引
        self.bm25 = None
        self.bm25_documents = []
        self.bm25_doc_ids = []
        self.bm25_metadatas = []

        # RRF 参数
        self.rrf_k = 60  # RRF 常数

    def build_bm25_index(self, documents: List[Dict]):
        """
        构建 BM25 索引

        Args:
            documents: 文档列表，每个包含 "doc_id", "content", "metadata"
        """
        self.bm25_documents = [doc["content"] for doc in documents]
        self.bm25_doc_ids = [doc["doc_id"] for doc in documents]
        self.bm25_metadatas = [doc["metadata"] for doc in documents]

        # 分词并构建索引
        tokenized_docs = [list(jieba.cut_for_search(doc)) for doc in self.bm25_documents]
        self.bm25 = BM25Okapi(tokenized_docs)

    def search(self, query: str,
               n_results: int = 5,
               top_k_for_rerank: int = 20,
               filters: Optional[Dict] = None,
               enable_vector: bool = True,
               enable_bm25: bool = True,
               enable_metadata: bool = True) -> List[Dict]:
        """
        混合检索

        Args:
            query: 查询文本
            n_results: 返回结果数
            top_k_for_rerank: 用于 RRF 融合的候选数（每路）
            filters: 元数据过滤条件
            enable_vector: 是否启用向量检索
            enable_bm25: 是否启用 BM25 检索
            enable_metadata: 是否启用元数据匹配

        Returns:
            融合后的检索结果
        """
        all_results = {}  # doc_id -> result

        # 第1路：向量语义检索
        if enable_vector:
            vector_results = self._vector_search(query, top_k_for_rerank, filters)
            self._merge_results(all_results, vector_results, weight=1.0)

        # 第2路：BM25 关键词检索
        if enable_bm25 and self.bm25:
            bm25_results = self._bm25_search(query, top_k_for_rerank, filters)
            self._merge_results(all_results, bm25_results, weight=1.0)

        # 第3路：元数据匹配
        if enable_metadata:
            metadata_results = self._metadata_search(query, top_k_for_rerank, filters)
            self._merge_results(all_results, metadata_results, weight=1.5)  # 元数据匹配权重更高

        # 转换为列表并排序
        results = list(all_results.values())
        results.sort(key=lambda x: x["hybrid_score"], reverse=True)

        return results[:n_results]

    def _vector_search(self, query: str, n_results: int,
                       filters: Optional[Dict] = None) -> List[Dict]:
        """向量语义检索"""
        query_embedding = self.embedder.encode_single(query, normalize=True)

        query_params = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"]
        }

        if filters:
            query_params["where"] = filters

        results = self.vector_store.query(**query_params)

        formatted = []
        if results["documents"][0]:
            for i, (doc_id, doc, metadata, distance) in enumerate(zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            )):
                formatted.append({
                    "doc_id": doc_id,
                    "content": doc,
                    "metadata": metadata,
                    "vector_score": 1 - distance,  # 转相似度
                    "rank": i,
                    "source": "vector"
                })

        return formatted

    def _bm25_search(self, query: str, n_results: int,
                     filters: Optional[Dict] = None) -> List[Dict]:
        """BM25 关键词检索"""
        if not self.bm25:
            return []

        query_tokens = list(jieba.cut_for_search(query))
        scores = self.bm25.get_scores(query_tokens)

        results = []
        for i, score in enumerate(scores):
            results.append({
                "doc_id": self.bm25_doc_ids[i],
                "content": self.bm25_documents[i],
                "metadata": self.bm25_metadatas[i],
                "bm25_score": float(score),
                "rank": i,
                "source": "bm25"
            })

        results.sort(key=lambda x: x["bm25_score"], reverse=True)

        if filters:
            results = self._apply_filters(results, filters)

        return results[:n_results]

    def _metadata_search(self, query: str, n_results: int,
                        filters: Optional[Dict] = None) -> List[Dict]:
        """元数据匹配检索（标题、标签等）"""
        # 获取所有文档
        try:
            all_docs = self.vector_store.get()
        except Exception:
            return []

        if not all_docs.get("ids"):
            return []

        results = []
        query_lower = query.lower()

        for i, (doc_id, doc, metadata) in enumerate(zip(
            all_docs["ids"],
            all_docs["documents"],
            all_docs["metadatas"]
        )):
            score = 0.0

            # 标题匹配
            title = metadata.get("title", "")
            if query_lower in title.lower():
                score += 10.0

            # 标签匹配
            tags = metadata.get("tags", "")
            if tags and query_lower in tags.lower():
                score += 5.0

            # 模块匹配
            module = metadata.get("module", "")
            if query_lower in module.lower():
                score += 3.0

            if score > 0:
                results.append({
                    "doc_id": doc_id,
                    "content": doc,
                    "metadata": metadata,
                    "metadata_score": score,
                    "rank": len(results),
                    "source": "metadata"
                })

        results.sort(key=lambda x: x["metadata_score"], reverse=True)
        return results[:n_results]

    def _merge_results(self, merged: Dict, new_results: List[Dict],
                       weight: float = 1.0):
        """
        使用 RRF (Reciprocal Rank Fusion) 融合多路结果

        RRF(d) = Σ (1 / (k + rank(d)))
        """
        for result in new_results:
            doc_id = result["doc_id"]
            rank = result["rank"] + 1  # rank 从 1 开始
            rrf_score = weight / (self.rrf_k + rank)

            if doc_id in merged:
                merged[doc_id]["hybrid_score"] += rrf_score
                # 保留最高分数来源
                merged[doc_id]["sources"].append(result["source"])
            else:
                merged[doc_id] = {
                    **result,
                    "hybrid_score": rrf_score,
                    "sources": [result["source"]]
                }

    def _apply_filters(self, results: List[Dict],
                       filters: Dict) -> List[Dict]:
        """应用元数据过滤"""
        filtered = []
        for result in results:
            match = True
            for key, value in filters.items():
                metadata_value = result["metadata"].get(key)
                if metadata_value != value:
                    match = False
                    break
            if match:
                filtered.append(result)
        return filtered
