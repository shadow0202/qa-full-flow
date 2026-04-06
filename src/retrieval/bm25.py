"""BM25 检索器 - 关键词匹配"""
import jieba
from typing import List, Dict, Optional
from rank_bm25 import BM25Okapi


class BM25Retriever:
    """
    BM25 关键词检索器

    使用 jieba 分词 + BM25 算法实现关键词匹配
    与向量检索互补，提升关键词精确匹配的召回率
    """

    def __init__(self):
        self.bm25 = None
        self.documents = []
        self.doc_ids = []
        self.metadatas = []

    def build_index(self, documents: List[str], doc_ids: List[str] = None,
                    metadatas: List[Dict] = None):
        """
        构建 BM25 索引

        Args:
            documents: 文档文本列表
            doc_ids: 文档 ID 列表
            metadatas: 元数据列表
        """
        self.documents = documents
        self.doc_ids = doc_ids or [f"doc_{i}" for i in range(len(documents))]
        self.metadatas = metadatas or [{} for _ in range(len(documents))]

        # 使用 jieba 分词
        tokenized_docs = [list(jieba.cut_for_search(doc)) for doc in documents]
        self.bm25 = BM25Okapi(tokenized_docs)

    def search(self, query: str,
               n_results: int = 5,
               filters: Optional[Dict] = None) -> List[Dict]:
        """
        BM25 关键词检索

        Args:
            query: 查询文本
            n_results: 返回结果数
            filters: 过滤条件

        Returns:
            检索结果列表
        """
        if not self.bm25:
            raise RuntimeError("BM25 索引未构建，请先调用 build_index()")

        # 分词
        query_tokens = list(jieba.cut_for_search(query))

        # 获取 BM25 分数
        scores = self.bm25.get_scores(query_tokens)

        # 构建结果列表
        results = []
        for i, score in enumerate(scores):
            results.append({
                "doc_id": self.doc_ids[i],
                "content": self.documents[i],
                "metadata": self.metadatas[i],
                "bm25_score": float(score),
                "rank": i
            })

        # 按分数排序
        results.sort(key=lambda x: x["bm25_score"], reverse=True)

        # 应用过滤
        if filters:
            results = self._apply_filters(results, filters)

        # 返回 top-n
        return results[:n_results]

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
