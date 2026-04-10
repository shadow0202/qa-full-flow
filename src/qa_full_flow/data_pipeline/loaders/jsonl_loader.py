"""JSONL格式数据加载器"""
import json
import logging
from pathlib import Path
from typing import List, Dict
import jieba.analyse
from src.qa_full_flow.data_pipeline.loaders.base import BaseLoader

logger = logging.getLogger(__name__)


class JSONLLoader(BaseLoader):
    """JSONL格式数据加载器"""
    
    def load(self, source: str) -> List[Dict]:
        """
        加载JSONL文件
        
        Args:
            source: JSONL文件路径
            
        Returns:
            文档列表
        """
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"JSONL文件不存在: {source}")
        
        documents = []
        with open(source_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    item = json.loads(line)
                    doc = self._parse_item(item)
                    documents.append(doc)
                except json.JSONDecodeError as e:
                    logger.warning(f"跳过第{line_num}行（JSON解析失败）: {e}")

        logger.info(f"JSONL加载完成: {len(documents)} 条文档")
        return documents
    
    def _parse_item(self, item: Dict) -> Dict:
        """解析单条JSONL记录"""
        metadata = item.get("metadata", {}).copy()
        # 确保 last_updated 存在，否则使用当前时间
        if "last_updated" not in metadata:
            from datetime import datetime
            metadata["last_updated"] = datetime.now().isoformat()

        # 获取原始 tags
        tags = item.get("tags", [])
        content = item.get("content", "")

        # 如果 tags 为空，自动提取关键词
        if not tags and content:
            tags = self._extract_keywords(content, top_k=10)

        return {
            "doc_id": item.get("doc_id", ""),
            "content": content,
            "source_type": item.get("source_type", "unknown"),
            "module": item.get("module", "unknown"),
            "tags": tags,
            "metadata": metadata
        }

    def _extract_keywords(self, content: str, top_k: int = 10) -> List[str]:
        """
        从文档内容中提取关键词（使用 TF-IDF 算法）

        Args:
            content: 文档内容
            top_k: 提取关键词数量

        Returns:
            关键词列表
        """
        try:
            # 使用 jieba 的 TF-IDF 算法提取关键词
            keywords = jieba.analyse.extract_tags(content, topK=top_k, withWeight=False)
            return keywords
        except Exception as e:
            logger.warning(f"关键词提取失败: {e}")
            return []
