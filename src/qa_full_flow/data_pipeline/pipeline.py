"""数据管道 - 编排数据加载、向量化和入库"""
import logging
from datetime import datetime
from typing import List, Dict, Optional
from src.qa_full_flow.data_pipeline.loaders.base import BaseLoader
from src.qa_full_flow.data_pipeline.chunker import RecursiveCharacterSplitter
from src.qa_full_flow.embedding.embedder import Embedder
from src.qa_full_flow.vector_store.chroma_store import ChromaStore

logger = logging.getLogger(__name__)


class DataPipeline:
    """数据处理管道"""

    def __init__(
        self,
        embedder: Embedder,
        vector_store: ChromaStore,
        chunker: Optional[RecursiveCharacterSplitter] = None,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.chunker = chunker  # 可选，None 表示不切分

    def ingest(self, loader: BaseLoader, source: str, skip_existing: bool = True,
               update_mode: str = "incremental", chunker: Optional[RecursiveCharacterSplitter] = None) -> Dict:
        """
        执行数据入库

        Args:
            loader: 数据加载器
            source: 数据源路径
            skip_existing: 是否跳过已存在的数据（兼容旧接口）
            update_mode: 更新模式
                - "skip": 跳过已存在的（等同 skip_existing=True）
                - "incremental": 增量更新，对比 last_updated 时间戳
                - "force": 强制更新，覆盖所有数据
            chunker: 文档切分器（可选，传入则使用此实例而非全局默认）

        Returns:
            入库统计信息
        """
        logger.info("开始数据入库...")

        # 使用传入的 chunker 或默认
        active_chunker = chunker or self.chunker

        # 1. 加载数据
        documents = loader.load(source)

        if not documents:
            logger.warning("没有可入库的数据")
            return {"loaded": 0, "ingested": 0, "skipped": 0, "updated": 0}

        # 2. 检查已存在的文档
        if skip_existing or update_mode == "skip":
            existing_ids = self._get_existing_ids()
            new_docs = [doc for doc in documents if doc["doc_id"] not in existing_ids]
            skipped_count = len(documents) - len(new_docs)
            logger.info(f"新文档: {len(new_docs)}, 已存在: {skipped_count}")
        elif update_mode == "incremental":
            # 增量更新：对比时间戳
            new_docs, skipped_count, updated_count = self._check_for_updates(documents)
            logger.info(f"新文档: {len(new_docs)}, 需更新: {updated_count}, 已最新: {skipped_count}")
        else:
            # force 模式：全部更新
            new_docs = documents
            skipped_count = 0
            logger.info(f"强制更新模式: {len(documents)} 条文档")

        if not new_docs:
            logger.info("所有数据已是最新，跳过入库")
            return {
                "loaded": len(documents),
                "ingested": 0,
                "skipped": skipped_count,
                "updated": 0
            }

        # 3. 文档切分（如果启用了 chunker）
        if active_chunker:
            logger.info("正在切分文档...")
            new_docs = active_chunker.split_documents(new_docs)
            logger.info(f"切分结果: {len(documents)} 条文档 → {len(new_docs)} 个块")

        # 4. 向量化
        logger.info(f"正在向量化 {len(new_docs)} 条文档...")
        contents = [doc["content"] for doc in new_docs]
        embeddings = self.embedder.encode(contents, normalize=True)

        # 5. 构建元数据
        metadatas = []
        for doc in new_docs:
            metadata = {
                "source_type": doc["source_type"],
                "module": doc["module"],
                "tags": ",".join(doc["tags"]) if isinstance(doc["tags"], list) else doc["tags"],
                "priority": doc["metadata"].get("priority", "unknown"),
                "version": doc["metadata"].get("version", ""),
                "author": doc["metadata"].get("author", ""),
                "create_date": doc["metadata"].get("create_date", ""),
                "last_updated": doc["metadata"].get("last_updated", ""),
                "synced_at": datetime.now().isoformat(),
            }
            if "chunk_id" in doc:
                metadata["chunk_id"] = doc["chunk_id"]
                metadata["chunk_index"] = doc["chunk_index"]
                metadata["total_chunks"] = doc["total_chunks"]
            metadatas.append(metadata)

        # 6. 写入向量库
        logger.info("正在写入向量库...")
        ids = [doc["doc_id"] for doc in new_docs]
        self.vector_store.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=contents,
            metadatas=metadatas
        )

        logger.info(f"入库完成: {len(new_docs)} 条新文档")

        return {
            "loaded": len(documents),
            "ingested": len(new_docs),
            "skipped": skipped_count,
            "updated": len(new_docs)  # 简化统计，实际应该区分新增和更新
        }

    def rebuild_bm25_index(self, retriever) -> int:
        """
        重建 BM25 索引并保存（统一入口）

        Args:
            retriever: Retriever 实例（用于调用 build_bm25_index 和 save_bm25_index）

        Returns:
            重建的文档数量
        """
        try:
            all_docs = self.vector_store.get()
            if not all_docs.get("ids"):
                logger.warning("向量库中无文档，跳过 BM25 索引重建")
                return 0

            documents = [
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

            retriever.build_bm25_index(documents)
            retriever.save_bm25_index()
            logger.info(f"BM25 索引已重建并保存，共 {len(documents)} 个文档")
            return len(documents)

        except Exception as e:
            logger.error(f"BM25 索引重建失败: {e}")
            return 0

    def _get_existing_ids(self) -> set:
        """获取已存在的文档ID"""
        try:
            result = self.vector_store.get()
            return set(result.get("ids", []))
        except Exception:
            return set()

    def _check_for_updates(self, documents: List[Dict]) -> tuple:
        """
        检查哪些文档需要更新（对比 last_updated 时间戳）

        Returns:
            (new_docs, skipped_count, updated_count)
        """
        try:
            existing = self.vector_store.get()
        except Exception:
            # 如果获取失败，当作全部需要更新
            return documents, 0, len(documents)

        # 构建已存在文档的映射 {doc_id: metadata}
        existing_map = {}
        if existing.get("ids"):
            for doc_id, metadata in zip(existing["ids"], existing.get("metadatas", [])):
                existing_map[doc_id] = metadata

        new_docs = []
        skipped_count = 0
        updated_count = 0

        for doc in documents:
            doc_id = doc["doc_id"]
            source_updated = doc["metadata"].get("last_updated", "")

            if doc_id not in existing_map:
                # 新文档
                new_docs.append(doc)
                updated_count += 1
            else:
                # 已存在，对比更新时间
                existing_meta = existing_map[doc_id]
                existing_updated = existing_meta.get("last_updated", "")

                if self._is_newer(source_updated, existing_updated):
                    # 数据源有更新，需要更新
                    new_docs.append(doc)
                    updated_count += 1
                    logger.info(f"文档 {doc_id} 有更新: {existing_updated} → {source_updated}")
                else:
                    # 已是最新，跳过
                    skipped_count += 1

        return new_docs, skipped_count, updated_count

    def _is_newer(self, source_time: str, existing_time: str) -> bool:
        """
        比较时间戳，判断是否需要更新
        支持 ISO 8601 格式
        """
        if not source_time:
            return False
        if not existing_time:
            return True

        try:
            # 简化比较：直接字符串比较（ISO 8601 格式可直接比较）
            # 例如: "2026-04-08T10:00:00.000Z"
            return source_time > existing_time
        except Exception:
            # 如果解析失败，当作需要更新处理
            return True
