"""数据加载器基础接口"""
from abc import ABC, abstractmethod
from typing import List, Dict


class BaseLoader(ABC):
    """数据加载器抽象基类"""
    
    @abstractmethod
    def load(self, source: str) -> List[Dict]:
        """
        加载数据
        
        Args:
            source: 数据源路径或标识
            
        Returns:
            文档列表，每个文档包含:
            - doc_id: 唯一标识
            - content: 文档内容
            - source_type: 来源类型
            - module: 模块
            - tags: 标签列表
            - metadata: 其他元数据
        """
        pass
