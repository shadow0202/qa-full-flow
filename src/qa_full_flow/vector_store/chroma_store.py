"""ChromaDB向量存储封装"""
import logging
from typing import List, Dict, Optional, Any
import chromadb
from src.qa_full_flow.core.config import settings

logger = logging.getLogger(__name__)


class ChromaStore:
    """ChromaDB向量存储管理"""

    def __init__(self, path: Optional[str] = None, collection_name: Optional[str] = None) -> None:
        self.path = path or settings.CHROMA_PATH
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME

        try:
            logger.info(f"正在初始化ChromaDB: {self.path}")
            self.client = chromadb.PersistentClient(path=self.path)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB集合已就绪: {self.collection_name} (当前数据量: {self.collection.count()})")
        except Exception as e:
            logger.error(f"ChromaDB初始化失败: {e}")
            raise

    def count(self) -> int:
        """获取集合中文档数量"""
        return self.collection.count()

    def upsert(self, ids: List[str], embeddings: List[List[float]],
               documents: List[str], metadatas: List[Dict[str, Any]]) -> None:
        """
        插入或更新文档

        Args:
            ids: 文档ID列表
            embeddings: 向量列表
            documents: 文档内容列表
            metadatas: 元数据列表

        Raises:
            Exception: 写入失败时抛出异常
        """
        try:
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            logger.debug(f"成功upsert {len(ids)} 个文档")
        except Exception as e:
            logger.error(f"ChromaDB upsert失败: {e}")
            raise
    
    def query(self, query_embeddings: List[List[float]], 
              n_results: int = 5,
              where: Optional[Dict[str, Any]] = None,
              include: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        查询相似文档

        Args:
            query_embeddings: 查询向量列表
            n_results: 返回结果数
            where: 过滤条件
            include: 包含字段 ["documents", "metadatas", "distances"]

        Returns:
            查询结果

        Raises:
            Exception: 查询失败时抛出异常
        """
        try:
            if include is None:
                include = ["documents", "metadatas", "distances"]

            query_params: Dict[str, Any] = {
                "query_embeddings": query_embeddings,
                "n_results": n_results,
                "include": include
            }

            if where:
                query_params["where"] = where

            return self.collection.query(**query_params)
        except Exception as e:
            logger.error(f"ChromaDB查询失败: {e}")
            raise

    def get(self, ids: Optional[List[str]] = None, 
            where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取文档"""
        params: Dict[str, Any] = {}
        if ids:
            params["ids"] = ids
        if where:
            params["where"] = where

        return self.collection.get(**params)

    def delete(self, ids: Optional[List[str]] = None) -> None:
        """删除文档"""
        if ids:
            self.collection.delete(ids=ids)

    def get_collection_info(self) -> Dict[str, Any]:
        """获取集合信息"""
        return {
            "name": self.collection_name,
            "count": self.collection.count(),
            "path": self.path
        }
