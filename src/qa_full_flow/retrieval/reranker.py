"""Cross-Encoder 重排序器 - 精确相关性打分"""
from typing import List, Dict, Optional
from sentence_transformers import CrossEncoder
from src.qa_full_flow.core.config import settings


class Reranker:
    """
    Cross-Encoder 重排序器

    使用 Cross-Encoder 模型对候选结果进行精确的相关性打分
    相比 Bi-Encoder（向量检索），Cross-Encoder 能捕捉 query-document 的细粒度交互
    """

    def __init__(self, model_name: str = None, device: str = None):
        """
        初始化重排序器

        Args:
            model_name: Cross-Encoder 模型名称
            device: 计算设备
        """
        self.model_name = model_name or settings.RERANKER_MODEL
        self.device = device or settings.RERANKER_DEVICE

        print(f"📥 正在加载Reranker模型: {self.model_name} (device={self.device})")
        self.model = CrossEncoder(self.model_name, device=self.device)
        print("✅ Reranker模型加载完成")

    def rerank(self, query: str, documents: List[Dict],
               top_k: Optional[int] = None) -> List[Dict]:
        """
        对候选文档进行重排序

        Args:
            query: 查询文本
            documents: 候选文档列表（需包含 "content" 字段）
            top_k: 返回前 k 个结果，None 表示返回全部

        Returns:
            重排序后的文档列表（按相关性降序排列）
        """
        if not documents:
            return []

        # 构建 query-document 对
        sentence_pairs = [(query, doc["content"]) for doc in documents]

        # 获取相关性分数
        scores = self.model.predict(sentence_pairs, show_progress_bar=False)

        # 附加分数到结果
        results = []
        for i, (doc, score) in enumerate(zip(documents, scores)):
            result = doc.copy()
            result["rerank_score"] = float(score)
            result["rank"] = i
            results.append(result)

        # 按 rerank_score 降序排序
        results.sort(key=lambda x: x["rerank_score"], reverse=True)

        # 返回 top-k
        if top_k is not None:
            return results[:top_k]
        return results

    def batch_rerank(self, queries: List[str],
                     document_lists: List[List[Dict]],
                     top_k: Optional[int] = None) -> List[List[Dict]]:
        """
        批量重排序

        Args:
            queries: 查询文本列表
            document_lists: 每个查询对应的候选文档列表
            top_k: 每个查询返回的前 k 个结果

        Returns:
            每个查询的重排序结果列表
        """
        results = []
        for query, docs in zip(queries, document_lists):
            reranked = self.rerank(query, docs, top_k)
            results.append(reranked)
        return results
