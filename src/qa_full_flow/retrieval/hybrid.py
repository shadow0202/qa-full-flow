"""混合检索器 - 多路召回 + RRF 融合"""
import os
import json
import logging
import jieba
from typing import List, Dict, Optional
from pathlib import Path
from rank_bm25 import BM25Okapi
from src.qa_full_flow.vector_store.chroma_store import ChromaStore
from src.qa_full_flow.embedding.embedder import Embedder

logger = logging.getLogger(__name__)

# 安全配置：默认禁用不安全的 pickle 加载
_ALLOW_PICKLE_LOADING = os.getenv("ALLOW_PICKLE_LOADING", "false").lower() == "true"


class HybridRetriever:
    """
    混合检索器

    多路召回策略：
    1. 向量语义路：SentenceTransformer + ChromaDB
    2. BM25关键词路：jieba分词 + BM25
    3. 元数据匹配路：标题、标签精确匹配

    使用 RRF (Reciprocal Rank Fusion) 融合多路结果
    """

    # 元数据匹配权重（高于向量和BM25，因为模块/标签精确匹配相关性更强）
    METADATA_SEARCH_WEIGHT = 1.5

    def __init__(self, embedder: Embedder, vector_store: ChromaStore,
                 index_path: Optional[str] = None):
        """
        初始化混合检索器

        Args:
            embedder: Embedding 模型
            vector_store: 向量数据库
            index_path: BM25 索引文件路径（默认: ./data/vector_db/bm25_index.json）
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

        # BM25 索引文件路径
        if index_path is None:
            from src.qa_full_flow.core.config import settings
            index_dir = Path(settings.CHROMA_PATH).parent
            index_dir.mkdir(parents=True, exist_ok=True)
            self.index_path = str(index_dir / "bm25_index.json")
        else:
            self.index_path = index_path

        # 元数据检索索引缓存（避免每次查询都重建）
        self._metadata_module_index: Dict[str, List[int]] = {}
        self._metadata_tag_index: Dict[str, List[int]] = {}
        self._metadata_indexed = False
        
        # 索引一致性追踪
        self._last_vector_store_count = 0
        self._index_dirty = False

    def build_bm25_index(self, documents: List[Dict]):
        """
        构建 BM25 索引

        Args:
            documents: 文档列表，每个包含 "doc_id", "content", "metadata"
        """
        logger.info(f"🔨 正在构建 BM25 索引，共 {len(documents)} 个文档...")
        self.bm25_documents = [doc["content"] for doc in documents]
        self.bm25_doc_ids = [doc["doc_id"] for doc in documents]
        self.bm25_metadatas = [doc["metadata"] for doc in documents]

        # 分词并构建索引
        tokenized_docs = [list(jieba.cut_for_search(doc)) for doc in self.bm25_documents]
        self.bm25 = BM25Okapi(tokenized_docs)
        
        # 重置元数据索引标记
        self._metadata_indexed = False
        self._index_dirty = False
        self._last_vector_store_count = len(documents)
        
        logger.info("BM25 索引构建完成")

    def save_bm25_index(self) -> bool:
        """
        保存 BM25 索引到文件（使用 JSON 格式，避免 pickle 安全风险）

        Returns:
            是否保存成功
        """
        if self.bm25 is None:
            logger.warning("BM25 索引未构建，无法保存")
            return False

        try:
            # 确保目录存在
            index_dir = Path(self.index_path).parent
            index_dir.mkdir(parents=True, exist_ok=True)

            # 注意：BM25Okapi 对象无法直接 JSON 序列化
            # 我们保存重建所需的数据，加载时重新构建
            index_data = {
                "documents": self.bm25_documents,
                "doc_ids": self.bm25_doc_ids,
                "metadatas": self.bm25_metadatas,
            }

            # 使用 JSON 格式（安全、可读、跨语言）
            json_path = self.index_path.replace(".pkl", ".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)

            # 同时更新 .pkl 路径指向（兼容旧代码）
            self.index_path = json_path

            logger.info(f"BM25 索引已保存到: {json_path}")
            return True

        except Exception as e:
            logger.error(f"BM25 索引保存失败: {e}", exc_info=True)
            return False

    def load_bm25_index(self) -> bool:
        """
        从文件加载 BM25 索引（支持 JSON 和旧 pickle 格式）

        Returns:
            是否加载成功
        """
        # 优先加载 JSON 格式
        json_path = self.index_path.replace(".pkl", ".json")
        if os.path.exists(json_path):
            return self._load_from_json(json_path)

        # 兼容旧 pickle 格式（警告：默认禁用以防止安全风险）
        if _ALLOW_PICKLE_LOADING and os.path.exists(self.index_path):
            logger.warning(
                f"检测到旧格式索引 {self.index_path}，建议重新构建。"
                f"如需加载请设置环境变量 ALLOW_PICKLE_LOADING=true（存在安全风险）"
            )
            return self._load_from_pickle()

        logger.info(f"BM25 索引文件不存在: {json_path}")
        return False

    def _load_from_json(self, json_path: str) -> bool:
        """从 JSON 文件加载索引"""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)

            self.bm25_documents = index_data["documents"]
            self.bm25_doc_ids = index_data["doc_ids"]
            self.bm25_metadatas = index_data["metadatas"]

            # 重新构建 BM25 索引
            tokenized_docs = [list(jieba.cut_for_search(doc)) for doc in self.bm25_documents]
            self.bm25 = BM25Okapi(tokenized_docs)

            self.index_path = json_path
            logger.info(f"BM25 索引已加载: {json_path} "
                       f"(共 {len(self.bm25_doc_ids)} 个文档)")
            return True

        except Exception as e:
            logger.warning(f"BM25 索引加载失败: {e}", exc_info=True)
            return False

    def _load_from_pickle(self) -> bool:
        """从旧 pickle 文件加载（兼容模式）"""
        try:
            import pickle
            with open(self.index_path, "rb") as f:
                index_data = pickle.load(f)

            self.bm25 = index_data.get("bm25")
            self.bm25_documents = index_data.get("documents", [])
            self.bm25_doc_ids = index_data.get("doc_ids", [])
            self.bm25_metadatas = index_data.get("metadatas", [])

            logger.warning(f"⚠️  已加载旧格式索引，建议调用 save_bm25_index() 转换为新格式")
            return True

        except Exception as e:
            logger.warning(f"⚠️  旧格式索引加载失败: {e}")
            return False

    def search(self, query: str,
               n_results: int = 5,
               top_k_for_rerank: int = 20,
               filters: Optional[Dict] = None,
               enable_vector: bool = True,
               enable_bm25: bool = True,
               enable_metadata: bool = True,
               bm25_query: Optional[str] = None,
               metadata_query: Optional[str] = None) -> List[Dict]:
        """
        混合检索

        Args:
            query: 查询文本（默认用于向量检索）
            n_results: 返回结果数
            top_k_for_rerank: 用于 RRF 融合的候选数（每路）
            filters: 元数据过滤条件
            enable_vector: 是否启用向量检索
            enable_bm25: 是否启用 BM25 检索
            enable_metadata: 是否启用元数据匹配
            bm25_query: BM25 检索专用 query（默认使用 query）
            metadata_query: 元数据检索专用 query（默认使用 query）

        Returns:
            融合后的检索结果
        """
        # 检查索引一致性，如果向量库文档数量变化则标记为脏
        current_count = self.vector_store.count()
        if current_count != self._last_vector_store_count:
            self._index_dirty = True
            self._metadata_indexed = False
        
        # 如果不传专用 query，默认使用主 query
        actual_bm25_query = bm25_query or query
        actual_metadata_query = metadata_query or query

        all_results = {}  # doc_id -> result

        # 第1路：向量语义检索
        if enable_vector:
            vector_results = self._vector_search(query, top_k_for_rerank, filters)
            self._merge_results(all_results, vector_results, weight=1.0)

        # 第2路：BM25 关键词检索
        if enable_bm25 and self.bm25:
            bm25_results = self._bm25_search(actual_bm25_query, top_k_for_rerank, filters)
            self._merge_results(all_results, bm25_results, weight=1.0)

        # 第3路：元数据匹配
        if enable_metadata:
            metadata_results = self._metadata_search(actual_metadata_query, top_k_for_rerank, filters)
            self._merge_results(all_results, metadata_results, weight=self.METADATA_SEARCH_WEIGHT)

        # 转换为列表并排序
        results = list(all_results.values())
        results.sort(key=lambda x: x["hybrid_score"], reverse=True)
        
        # 记录检索统计
        if results:
            sources_count = {}
            for r in results[:n_results]:
                for s in r.get("sources", []):
                    sources_count[s] = sources_count.get(s, 0) + 1
            logger.debug(f"检索返回 {min(len(results), n_results)} 条结果，来源分布: {sources_count}")

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
        """BM25 关键词检索（优化：先粗排取 Top-K，再计算精确分数）"""
        if not self.bm25:
            return []

        query_tokens = list(jieba.cut_for_search(query))
        
        # 优化：先获取所有分数，但只保留 Top-K 候选
        # 避免对全量文档进行过滤和排序
        all_scores = self.bm25.get_scores(query_tokens)
        
        # 获取 Top-K 候选（K = n_results * 3，给过滤留出余量）
        top_k_candidates = min(len(all_scores), n_results * 3)
        top_indices = sorted(range(len(all_scores)), key=lambda i: all_scores[i], reverse=True)[:top_k_candidates]
        
        results = []
        for i in top_indices:
            score = all_scores[i]
            if score <= 0:
                continue
                
            result = {
                "doc_id": self.bm25_doc_ids[i],
                "content": self.bm25_documents[i],
                "metadata": self.bm25_metadatas[i],
                "bm25_score": float(score),
                "rank": len(results),
                "source": "bm25"
            }
            results.append(result)

        # 应用过滤条件
        if filters:
            results = self._apply_filters(results, filters)

        # 按分数重新排序并返回 Top-N
        results.sort(key=lambda x: x["bm25_score"], reverse=True)
        return results[:n_results]

    def _build_metadata_index(self, all_docs: Dict) -> None:
        """
        构建元数据索引（缓存到实例变量，避免每次查询都重建）

        Args:
            all_docs: 从向量库获取的所有文档
        """
        self._metadata_module_index.clear()
        self._metadata_tag_index.clear()

        for i, metadata in enumerate(all_docs.get("metadatas", [])):
            # 构建 module 索引
            module = metadata.get("module", "").strip()
            if module:
                module_lower = module.lower()
                if module_lower not in self._metadata_module_index:
                    self._metadata_module_index[module_lower] = []
                self._metadata_module_index[module_lower].append(i)

            # 构建 tags 索引
            tags = metadata.get("tags", "").strip()
            if tags:
                tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
                for tag in tag_list:
                    if tag not in self._metadata_tag_index:
                        self._metadata_tag_index[tag] = []
                    self._metadata_tag_index[tag].append(i)

        self._metadata_indexed = True

    def _metadata_search(self, query: str, n_results: int,
                        filters: Optional[Dict] = None) -> List[Dict]:
        """元数据匹配检索（模块、标签等）"""
        # 获取所有文档
        try:
            all_docs = self.vector_store.get()
        except Exception:
            return []

        if not all_docs.get("ids"):
            return []

        # 如果索引未构建，先构建
        if not self._metadata_indexed:
            self._build_metadata_index(all_docs)

        # 对查询文本分词
        query_tokens = list(jieba.cut_for_search(query))
        query_tokens = [t.strip().lower() for t in query_tokens if t.strip()]
        query_lower = query.lower()

        if not query_tokens:
            return []

        # 收集候选文档（只遍历匹配的文档，而非全量）
        candidate_indices = set()

        # 通过 module 索引查找
        for token in query_tokens:
            if token in self._metadata_module_index:
                candidate_indices.update(self._metadata_module_index[token])

        # 通过 tags 索引查找
        for token in query_tokens:
            if token in self._metadata_tag_index:
                candidate_indices.update(self._metadata_tag_index[token])
        
        # 通过 source_type 过滤（如果 filters 中有）
        if filters and "source_type" in filters:
            source_type_filter = filters["source_type"].lower()
            source_type_indices = set()
            for i, metadata in enumerate(all_docs.get("metadatas", [])):
                if metadata.get("source_type", "").lower() == source_type_filter:
                    source_type_indices.add(i)
            
            # 如果有 source_type 过滤，取交集
            if source_type_indices:
                if candidate_indices:
                    candidate_indices &= source_type_indices
                else:
                    candidate_indices = source_type_indices

        # 如果没有候选文档，返回空
        if not candidate_indices:
            return []

        results = []

        # 只对候选文档计算分数
        for i in candidate_indices:
            doc_id = all_docs["ids"][i]
            doc = all_docs["documents"][i]
            metadata = all_docs["metadatas"][i]

            score = 0.0

            # 模块精确匹配（权重最高）
            module = metadata.get("module", "").strip()
            if module:
                module_lower = module.lower()
                # 精确匹配（查询词等于模块名）
                if any(t == module_lower for t in query_tokens):
                    score += 20.0
                # 包含匹配（查询词是模块名的子串）
                elif any(t in module_lower for t in query_tokens):
                    score += 10.0
                # 反向包含匹配（模块名是查询词的子串）
                elif module_lower in query_lower:
                    score += 5.0

            # 标签匹配（按逗号拆分后匹配）
            tags = metadata.get("tags", "").strip()
            if tags:
                tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
                # 精确匹配标签
                for token in query_tokens:
                    if token in tag_list:
                        score += 5.0
                    # 标签包含查询词
                    elif any(token in tag for tag in tag_list):
                        score += 2.0

            if score > 0:
                # 应用其他过滤条件（除了 source_type 已处理）
                if filters:
                    match = True
                    for key, value in filters.items():
                        if key == "source_type":
                            continue  # 已处理
                        metadata_value = metadata.get(key)
                        if metadata_value != value:
                            match = False
                            break
                    if not match:
                        continue
                
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
        if not filters:
            return results
            
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
