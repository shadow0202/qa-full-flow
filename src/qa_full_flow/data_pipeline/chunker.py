"""递归字符切分器 - 支持 Markdown 标题/段落/句子多级切分"""
import re
from typing import List, Optional


class RecursiveCharacterSplitter:
    """
    递归字符切分器

    切分策略（按优先级）：
    1. 按 Markdown 一级标题 (# ) 切分
    2. 按 Markdown 二级标题 (## ) 切分
    3. 按 Markdown 三级标题 (### ) 切分
    4. 按段落 (\n\n) 切分
    5. 按句子 (. 。! ！? ？) 切分
    6. 按字符切分（保底）

    每个块设置重叠（overlap），防止关键信息被切断
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        length_function: Optional[callable] = None,
    ):
        """
        初始化切分器

        Args:
            chunk_size: 每个块的最大字符数
            chunk_overlap: 相邻块之间的重叠字符数
            length_function: 文本长度计算函数，默认使用 len()
        """
        if chunk_overlap >= chunk_size:
            raise ValueError(f"chunk_overlap ({chunk_overlap}) 必须小于 chunk_size ({chunk_size})")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.length_function = length_function or len

        # 切分器优先级列表（从粗到细）
        self.separators = [
            "\n# ",   # Markdown 一级标题
            "\n## ",  # Markdown 二级标题
            "\n### ", # Markdown 三级标题
            "\n\n",   # 段落
            "\n",     # 换行
            "。",     # 中文句号
            ".",      # 英文句号
            "！",     # 中文感叹号
            "!",      # 英文感叹号
            "？",     # 中文问号
            "?",      # 英文问号
            " ",      # 空格
            "",       # 字符（保底）
        ]

    def split_text(self, text: str) -> List[str]:
        """
        递归切分文本

        Args:
            text: 待切分的文本

        Returns:
            切分后的文本块列表
        """
        if not text or not text.strip():
            return []

        return self._split_text_recursive(text, self.separators)

    def _split_text_recursive(self, text: str, separators: List[str]) -> List[str]:
        """
        递归切分核心逻辑

        尝试使用当前层级的分隔符切分，如果单块仍超过 chunk_size，
        则递归使用下一层级的分隔符
        """
        final_chunks = []

        # 尝试使用当前层级的分隔符切分
        separator = separators[0]
        new_separators = separators[1:]

        if separator:
            # 使用正则表达式保留分隔符在下一个块的开头
            # 例如: "text\n\n# Title" -> ["text", "\n\n# Title"]
            if separator == "":
                # 字符级别切分，直接按字符拆分
                splits = list(text)
            else:
                splits = text.split(separator)
        else:
            splits = list(text)

        # 重新组合分隔符（保留分隔符语义）
        good_splits = []
        for i, split in enumerate(splits):
            if i < len(splits) - 1:
                # 除了最后一个，每个 split 后面加上分隔符
                current = split + separator
            else:
                current = split

            if self.length_function(current) <= self.chunk_size:
                good_splits.append(current)
            else:
                # 当前块太大
                if good_splits:
                    # 先合并已有的块
                    merged = self._merge_splits(good_splits, separator)
                    final_chunks.extend(merged)
                    good_splits = []

                # 递归处理这个太大的块
                if new_separators:
                    sub_chunks = self._split_text_recursive(current, new_separators)
                    final_chunks.extend(sub_chunks)
                else:
                    # 没有更细的切分方式，直接截断
                    final_chunks.append(current[:self.chunk_size])

        # 处理剩余的块
        if good_splits:
            merged = self._merge_splits(good_splits, separator)
            final_chunks.extend(merged)

        # 应用重叠
        final_chunks = self._apply_overlap(final_chunks)

        return final_chunks

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        """
        合并小块，确保不超过 chunk_size
        """
        if not splits:
            return []

        merged_chunks = []
        current_chunk = []
        current_length = 0

        for split in splits:
            split_len = self.length_function(split)

            # 如果当前块加上下一个 split 超过限制
            if current_length + split_len > self.chunk_size:
                if current_chunk:
                    # 保存当前块
                    merged_text = "".join(current_chunk).strip()
                    if merged_text:
                        merged_chunks.append(merged_text)
                    current_chunk = []
                    current_length = 0

            current_chunk.append(split)
            current_length += split_len

        # 处理最后一个块
        if current_chunk:
            merged_text = "".join(current_chunk).strip()
            if merged_text:
                merged_chunks.append(merged_text)

        return merged_chunks

    def _apply_overlap(self, chunks: List[str]) -> List[str]:
        """
        应用重叠策略，防止关键信息被切断

        例如：chunk_size=500, chunk_overlap=50
        每个块的前 50 个字符与前一个块的后 50 个字符重叠
        """
        if not chunks or self.chunk_overlap == 0:
            return chunks

        result = [chunks[0]]

        for i in range(1, len(chunks)):
            prev_chunk = result[-1]
            current_chunk = chunks[i]

            # 获取前一个块的末尾作为重叠部分
            overlap_text = prev_chunk[-self.chunk_overlap:]

            # 如果当前块不以重叠部分开头，添加重叠
            if not current_chunk.startswith(overlap_text):
                # 在块前面添加重叠内容
                current_chunk = overlap_text + current_chunk

            result.append(current_chunk)

        return result

    def split_documents(self, documents: List[dict]) -> List[dict]:
        """
        批量切分文档

        Args:
            documents: 文档列表，每个文档包含 "content" 和元数据

        Returns:
            切分后的文档列表，每个文档新增 "chunk_id" 和 "chunk_index" 字段
        """
        split_docs = []

        for doc in documents:
            content = doc.get("content", "")
            chunks = self.split_text(content)

            for idx, chunk in enumerate(chunks):
                split_doc = doc.copy()
                split_doc["content"] = chunk
                split_doc["doc_id"] = f"{doc['doc_id']}_chunk_{idx}"
                split_doc["chunk_id"] = doc["doc_id"]
                split_doc["chunk_index"] = idx
                split_doc["total_chunks"] = len(chunks)
                split_docs.append(split_doc)

        return split_docs
