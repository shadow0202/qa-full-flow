"""RecursiveCharacterSplitter 单元测试"""
import pytest
from src.data_pipeline.chunker import RecursiveCharacterSplitter


class TestRecursiveCharacterSplitter:
    """递归字符切分器测试"""

    def test_basic_split(self):
        """测试基础切分"""
        splitter = RecursiveCharacterSplitter(chunk_size=50, chunk_overlap=10)
        text = "这是第一段。\n\n这是第二段。\n\n这是第三段。"
        chunks = splitter.split_text(text)

        assert len(chunks) > 0
        assert all(len(chunk) <= 60 for chunk in chunks)  # 允许一定的弹性

    def test_markdown_heading_split(self):
        """测试 Markdown 标题切分"""
        splitter = RecursiveCharacterSplitter(chunk_size=100, chunk_overlap=10)
        text = """# 一级标题
这是一级标题下的内容。

## 二级标题
这是二级标题下的内容，比较长，需要超过一百个字才能测试切分逻辑是否正常工作。这里再补充一些文字确保长度足够。

### 三级标题
这是三级标题下的内容。
"""
        chunks = splitter.split_text(text)

        assert len(chunks) > 1
        # 检查标题是否被保留在块中
        assert any("# 一级标题" in chunk for chunk in chunks)

    def test_overlap(self):
        """测试重叠逻辑"""
        splitter = RecursiveCharacterSplitter(chunk_size=50, chunk_overlap=10)
        text = "A" * 100
        chunks = splitter.split_text(text)

        if len(chunks) > 1:
            # 检查相邻块是否有重叠
            for i in range(1, len(chunks)):
                prev_end = chunks[i - 1][-10:]
                curr_start = chunks[i][:10]
                # 重叠部分应该相同
                assert prev_end == curr_start or chunks[i].startswith(prev_end)

    def test_empty_text(self):
        """测试空文本"""
        splitter = RecursiveCharacterSplitter()
        assert splitter.split_text("") == []
        assert splitter.split_text("   \n  ") == []

    def test_short_text(self):
        """测试短文本（不超过 chunk_size）"""
        splitter = RecursiveCharacterSplitter(chunk_size=100, chunk_overlap=10)
        text = "这是一段很短的文本"
        chunks = splitter.split_text(text)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_documents(self):
        """测试文档批量切分"""
        splitter = RecursiveCharacterSplitter(chunk_size=50, chunk_overlap=10)
        documents = [
            {
                "doc_id": "DOC_001",
                "content": "这是第一篇文档内容。这里需要足够长才能测试切分逻辑。\n\n第二段内容。",
                "source_type": "test_case",
                "module": "测试模块",
                "tags": ["测试"],
                "metadata": {"priority": "P1"},
            },
            {
                "doc_id": "DOC_002",
                "content": "这是第二篇文档内容。",
                "source_type": "bug_report",
                "module": "缺陷模块",
                "tags": ["缺陷"],
                "metadata": {"priority": "P0"},
            },
        ]

        split_docs = splitter.split_documents(documents)

        assert len(split_docs) > len(documents)  # 切分后应该有更多文档
        # 检查 chunk 元数据
        for doc in split_docs:
            assert "chunk_id" in doc
            assert "chunk_index" in doc
            assert "total_chunks" in doc
            assert doc["doc_id"].startswith("DOC_")
            assert "_chunk_" in doc["doc_id"]

    def test_chunk_size_validation(self):
        """测试 chunk_size 和 chunk_overlap 的校验"""
        with pytest.raises(ValueError):
            RecursiveCharacterSplitter(chunk_size=50, chunk_overlap=50)

        with pytest.raises(ValueError):
            RecursiveCharacterSplitter(chunk_size=50, chunk_overlap=60)

    def test_chinese_sentence_split(self):
        """测试中文句子切分"""
        splitter = RecursiveCharacterSplitter(chunk_size=30, chunk_overlap=5)
        text = "这是第一句话。这是第二句话！这是第三句话？这是第四句话。"
        chunks = splitter.split_text(text)

        assert len(chunks) > 1
        # 检查标点符号是否被正确切分
        assert any("。" in chunk for chunk in chunks)

    def test_custom_length_function(self):
        """测试自定义长度函数"""
        # 使用字符数而不是字节数
        splitter = RecursiveCharacterSplitter(
            chunk_size=10,
            chunk_overlap=2,
            length_function=lambda x: len(x.encode("utf-8")),
        )
        text = "中文文本测试"
        chunks = splitter.split_text(text)

        assert len(chunks) > 0

    def test_long_paragraph_without_breaks(self):
        """测试长段落无换行符的切分"""
        splitter = RecursiveCharacterSplitter(chunk_size=50, chunk_overlap=10)
        text = "这是一段很长的文本，没有任何换行符，需要通过句号或者其他分隔符进行切分。为了保证测试有效性，这里需要添加更多的内容，使得文本长度远超chunk_size限制，从而触发切分逻辑。"
        chunks = splitter.split_text(text)

        assert len(chunks) > 1
        # 验证每个块不超过合理大小
        for chunk in chunks:
            assert len(chunk) <= 70  # 允许一定的弹性
