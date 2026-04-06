"""检索器 - 语义检索功能"""
from typing import List, Dict, Optional
from src.embedding.embedder import Embedder
from src.vector_store.chroma_store import ChromaStore


class Retriever:
    """知识库检索器"""
    
    def __init__(self, embedder: Embedder, vector_store: ChromaStore):
        self.embedder = embedder
        self.vector_store = vector_store
    
    def search(self, query: str, 
               n_results: int = 5,
               filters: Optional[Dict] = None,
               include_distances: bool = True) -> List[Dict]:
        """
        语义检索
        
        Args:
            query: 查询文本
            n_results: 返回结果数
            filters: 过滤条件 {"module": "订单支付", "source_type": "test_case"}
            include_distances: 是否包含距离
            
        Returns:
            检索结果列表
        """
        # 1. 向量化查询
        query_embedding = self.embedder.encode_single(query, normalize=True)
        
        # 2. 构建查询参数
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
        
        # 3. 执行查询
        results = self.vector_store.query(**query_params)
        
        # 4. 格式化结果
        formatted_results = self._format_results(results)
        
        return formatted_results
    
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
