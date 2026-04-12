"""
Confluence/JIRA 加载器集成测试

尝试使用真实凭据获取少量数据，以验证连接器是否工作正常
并展示实际获取的数据结构。
"""
import os
import pytest
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

from src.qa_full_flow.data_pipeline.loaders.confluence_loader import ConfluenceLoader
from src.qa_full_flow.data_pipeline.loaders.jira_loader import JiraLoader


class TestConfluenceIntegration:
    """Confluence 真实连接测试"""

    @pytest.fixture
    def loader(self):
        url = os.getenv("CONFLUENCE_URL")
        email = os.getenv("CONFLUENCE_EMAIL")
        token = os.getenv("CONFLUENCE_API_TOKEN")

        if not all([url, email, token]):
            pytest.skip("Confluence credentials not found in .env")

        return ConfluenceLoader(url=url, email=email, api_token=token)

    def test_connection(self, loader):
        """测试连接并打印结果"""
        print("\n" + "=" * 80)
        print("🔌 正在测试 Confluence 连接...")
        result = loader.test_connection()
        print(f"✅ 连接结果: {result}")
        assert result is True

    def test_fetch_single_page(self, loader):
        """获取单个页面并打印数据结构"""
        print("\n" + "=" * 80)
        print("📄 正在尝试获取 1 个 Confluence 页面...")

        # 尝试获取 1 个页面
        docs = loader.load(max_results=1)

        if not docs:
            print("⚠️  未找到任何页面 (可能是权限问题或空间为空)")
            pytest.skip("No pages found")

        doc = docs[0]
        print(f"\n✅ 成功获取文档: {doc['doc_id']}")
        print(f"📝 内容摘要: {doc['content'][:200]}...")
        print(f"🏷️ 标签: {doc['tags']}")
        print(f"📦 元数据: {doc['metadata']}")
        
        # 验证基本结构
        assert "doc_id" in doc
        assert "content" in doc
        assert "source_type" in doc
        assert "tags" in doc


class TestJiraIntegration:
    """JIRA 真实连接测试"""

    @pytest.fixture
    def loader(self):
        url = os.getenv("JIRA_URL")
        email = os.getenv("JIRA_EMAIL")
        token = os.getenv("JIRA_API_TOKEN")

        if not all([url, email, token]):
            pytest.skip("Jira credentials not found in .env")

        return JiraLoader(url=url, email=email, api_token=token)

    def test_connection(self, loader):
        """测试连接并打印结果"""
        print("\n" + "=" * 80)
        print("🔌 正在测试 JIRA 连接...")
        result = loader.test_connection()
        print(f"✅ 连接结果: {result}")
        assert result is True

    def test_fetch_single_issue(self, loader):
        """获取单个 Issue 并打印数据结构"""
        print("\n" + "=" * 80)
        print("🐛 正在尝试获取 1 个 JIRA Issue...")

        # 尝试获取 1 个 Bug
        docs = loader.load_bugs(max_results=1)

        if not docs:
            print("⚠️  未找到任何 Bug (可能是权限问题或项目无 Bug)")
            pytest.skip("No bugs found")

        doc = docs[0]
        print(f"\n✅ 成功获取文档: {doc['doc_id']}")
        print(f"📝 内容摘要: {doc['content'][:200]}...")
        print(f"🏷️ 标签: {doc['tags']}")
        print(f"📦 元数据: {doc['metadata']}")

        # 验证基本结构
        assert "doc_id" in doc
        assert "content" in doc
        assert "source_type" in doc
        assert "tags" in doc
