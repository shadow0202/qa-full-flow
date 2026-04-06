"""ChromaDB向量存储封装"""
from typing import List, Dict, Optional
import chromadb
from src.config import settings


class ChromaStore:
    """ChromaDB向量存储管理"""
    
    def __init__(self, path: str = None, collection_name: str = None):
        self.path = path or settings.CHROMA_PATH
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME
        
        print(f"📥 正在初始化ChromaDB: {self.path}")
        self.client = chromadb.PersistentClient(path=self.path)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        print(f"✅ ChromaDB集合已就绪: {self.collection_name} (当前数据量: {self.collection.count()})")
    
    def count(self) -> int:
        """获取集合中文档数量"""
        return self.collection.count()
    
    def upsert(self, ids: List[str], embeddings: List[List[float]], 
               documents: List[str], metadatas: List[Dict]):
        """
        插入或更新文档
        
        Args:
            ids: 文档ID列表
            embeddings: 向量列表
            documents: 文档内容列表
            metadatas: 元数据列表
        """
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
    
    def query(self, query_embeddings: List[List[float]], 
              n_results: int = 5,
              where: Optional[Dict] = None,
              include: Optional[List[str]] = None) -> Dict:
        """
        查询相似文档
        
        Args:
            query_embeddings: 查询向量列表
            n_results: 返回结果数
            where: 过滤条件
            include: 包含字段 ["documents", "metadatas", "distances"]
            
        Returns:
            查询结果
        """
        if include is None:
            include = ["documents", "metadatas", "distances"]
        
        query_params = {
            "query_embeddings": query_embeddings,
            "n_results": n_results,
            "include": include
        }
        
        if where:
            query_params["where"] = where
        
        return self.collection.query(**query_params)
    
    def get(self, ids: Optional[List[str]] = None, 
            where: Optional[Dict] = None) -> Dict:
        """获取文档"""
        params = {}
        if ids:
            params["ids"] = ids
        if where:
            params["where"] = where
        
        return self.collection.get(**params)
    
    def delete(self, ids: Optional[List[str]] = None):
        """删除文档"""
        if ids:
            self.collection.delete(ids=ids)
    
    def get_collection_info(self) -> Dict:
        """获取集合信息"""
        return {
            "name": self.collection_name,
            "count": self.collection.count(),
            "path": self.path
        }
