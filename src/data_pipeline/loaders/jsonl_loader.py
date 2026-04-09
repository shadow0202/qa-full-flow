"""JSONL格式数据加载器"""
import json
from pathlib import Path
from typing import List, Dict
from src.data_pipeline.loaders.base import BaseLoader


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
                    print(f"⚠️  跳过第{line_num}行（JSON解析失败）: {e}")
        
        print(f"✅ JSONL加载完成: {len(documents)} 条文档")
        return documents
    
    def _parse_item(self, item: Dict) -> Dict:
        """解析单条JSONL记录"""
        metadata = item.get("metadata", {}).copy()
        # 确保 last_updated 存在，否则使用当前时间
        if "last_updated" not in metadata:
            from datetime import datetime
            metadata["last_updated"] = datetime.now().isoformat()

        return {
            "doc_id": item.get("doc_id", ""),
            "content": item.get("content", ""),
            "source_type": item.get("source_type", "unknown"),
            "module": item.get("module", "unknown"),
            "tags": item.get("tags", []),
            "metadata": metadata
        }
