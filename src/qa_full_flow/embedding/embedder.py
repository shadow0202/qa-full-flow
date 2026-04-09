"""Embedding服务 - 负责文本向量化"""
from typing import List
from sentence_transformers import SentenceTransformer
from src.qa_full_flow.core.config import settings


class Embedder:
    """Embedding模型服务"""
    
    def __init__(self, model_name: str = None, device: str = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.device = device or settings.EMBEDDING_DEVICE
        
        print(f"📥 正在加载Embedding模型: {self.model_name} (device={self.device})")
        self.model = SentenceTransformer(self.model_name, device=self.device)
        print("✅ Embedding模型加载完成")
    
    def encode(self, texts: List[str], normalize: bool = True) -> List[List[float]]:
        """
        将文本列表转换为向量
        
        Args:
            texts: 文本列表
            normalize: 是否归一化
            
        Returns:
            向量列表
        """
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=normalize,
            show_progress_bar=False
        )
        return embeddings.tolist()
    
    def encode_single(self, text: str, normalize: bool = True) -> List[float]:
        """转换单个文本"""
        return self.encode([text], normalize=normalize)[0]
    
    def get_dimension(self) -> int:
        """获取向量维度"""
        return self.model.get_sentence_embedding_dimension()
