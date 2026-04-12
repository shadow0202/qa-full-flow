"""
ConfluenceLoader 和 JiraLoader 单元测试

测试从 Confluence 和 JIRA 获取信息的能力，使用 mock 避免真实网络请求。
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.qa_full_flow.data_pipeline.loaders.confluence_loader import ConfluenceLoader
from src.qa_full_flow.data_pipeline.loaders.jira_loader import JiraLoader


# ============================================================================
# ConfluenceLoader 测试
# ============================================================================

class TestConfluenceLoader:
    """Confluence 加载器测试"""

    @pytest.fixture
    def confluence_config(self):
        """Confluence 配置"""
        return {
            "url": "https://test.atlassian.net/wiki",
            "email": "test@test.com",
            "api_token": "test-token",
        }

    @pytest.fixture
    def loader(self, confluence_config):
        """ConfluenceLoader 实例"""
        return ConfluenceLoader(
            url=confluence_config["url"],
            email=confluence_config["email"],
            api_token=confluence_config["api_token"],
        )

    def test_init(self, confluence_config):
        """测试初始化"""
        loader = ConfluenceLoader(
            url=confluence_config["url"],
            email=confluence_config["email"],
            api_token=confluence_config["api_token"],
        )
        assert loader.url == "https://test.atlassian.net/wiki"
        assert loader.email == "test@test.com"
        assert loader.session is not None

    def test_close_releases_session(self, loader):
        """测试 close() 释放连接"""
        loader.session.close = Mock()
        loader.close()
        loader.session.close.assert_called_once()

    # ---------- 页面列表获取 ----------

    @patch("requests.Session.get")
    def test_fetch_pages_success(self, mock_get, loader):
        """测试获取页面列表成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"id": "111", "title": "Page 1"},
                {"id": "222", "title": "Page 2"},
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        pages = loader._fetch_pages(space_key="TEST", max_results=10)

        assert len(pages) == 2
        assert pages[0]["id"] == "111"
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args.kwargs["params"]["spaceKey"] == "TEST"
        assert call_args.kwargs["params"]["limit"] == 10

    @patch("requests.Session.get")
    def test_fetch_pages_api_error(self, mock_get, loader):
        """测试获取页面列表 API 错误"""
        mock_response = Mock()
        mock_response.raise_for_status = Mock(side_effect=Exception("API Error"))
        mock_get.return_value = mock_response

        with pytest.raises(Exception, match="API Error"):
            loader._fetch_pages(space_key="TEST", max_results=10)

    # ---------- 搜索页面 ----------

    @patch("requests.Session.get")
    def test_search_pages_success(self, mock_get, loader):
        """测试搜索页面成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{"id": "333", "title": "搜索到的页面"}]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        pages = loader._search_pages(query="测试", max_results=5)

        assert len(pages) == 1
        assert pages[0]["title"] == "搜索到的页面"

    @patch("requests.Session.get")
    def test_search_pages_error(self, mock_get, loader):
        """测试搜索页面失败"""
        mock_get.side_effect = Exception("Search failed")
        pages = loader._search_pages(query="测试", max_results=5)
        assert pages == []

    # ---------- 页面内容获取 ----------

    @patch("requests.Session.get")
    def test_get_page_body_success(self, mock_get, loader):
        """测试获取页面内容成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "body": {
                "storage": {
                    "value": "<h1>标题</h1><p>正文内容</p>",
                    "representation": "storage"
                }
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        body = loader._get_page_body(page_id="12345")

        assert "标题" in body
        assert "正文内容" in body

    @patch("requests.Session.get")
    def test_get_page_body_empty(self, mock_get, loader):
        """测试获取页面内容为空"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"body": {}}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        body = loader._get_page_body(page_id="12345")
        assert body == ""

    # ---------- 页面解析 ----------

    def test_parse_page_v2_api_format(self, loader):
        """测试解析 v2 API 格式的页面"""
        with patch.object(loader, "_get_page_body", return_value="<p>页面内容</p>"):
            page_data = {
                "id": "123456",
                "title": "测试文档",
                "spaceId": "TEST",
                "version": {
                    "number": 2,
                    "authorId": "user123",
                    "updatedAt": "2026-04-10T10:00:00.000Z",
                    "createdAt": "2026-04-01T08:00:00.000Z",
                },
            }

            doc = loader._parse_page(page_data)

            assert doc is not None
            assert doc["doc_id"] == "CONFL_123456"
            assert "测试文档" in doc["content"]
            assert doc["source_type"] == "test_case"  # 页面内容包含"页面内容"，被分类为 test_case
            assert doc["module"] == "TEST"
            assert doc["metadata"]["last_updated"] == "2026-04-10T10:00:00.000Z"
            assert doc["metadata"]["page_title"] == "测试文档"
            assert len(doc["tags"]) > 0  # 应自动提取关键词

    def test_parse_page_empty_body(self, loader):
        """测试解析空页面"""
        with patch.object(loader, "_get_page_body", return_value=""):
            doc = loader._parse_page({"id": "1", "title": "空页面"})
            assert doc is None

    # ---------- 关键词提取 ----------

    def test_extract_keywords(self, loader):
        """测试关键词提取"""
        content = "用户可以在订单页面选择微信支付、支付宝、银联三种支付方式"
        tags = loader._extract_keywords(content, top_k=5)

        assert isinstance(tags, list)
        assert len(tags) <= 5
        assert "支付" in tags  # 应提取"支付"

    def test_extract_keywords_empty(self, loader):
        """测试空内容关键词提取"""
        tags = loader._extract_keywords("", top_k=5)
        assert tags == []

    # ---------- 分类 ----------

    def test_classify_test_case(self, loader):
        """测试测试用例分类"""
        source_type = loader._classify_page("测试用例文档", "这是一个测试用例")
        assert source_type == "test_case"

    def test_classify_requirement(self, loader):
        """测试需求文档分类"""
        source_type = loader._classify_page("PRD 需求文档", "这是需求文档")
        assert source_type == "business_rule"

    def test_classify_bug(self, loader):
        """测试 Bug 文档分类"""
        source_type = loader._classify_page("缺陷报告", "这是一个 Bug")
        assert source_type == "bug_report"

    def test_classify_default(self, loader):
        """测试默认分类"""
        source_type = loader._classify_page("普通文档", "普通内容")
        assert source_type == "business_rule"

    # ---------- 连接测试 ----------

    @patch("requests.Session.get")
    def test_test_connection_success(self, mock_get, loader):
        """测试连接成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"title": "Page 1"}]}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        assert loader.test_connection() is True

    @patch("requests.Session.get")
    def test_test_connection_failure(self, mock_get, loader):
        """测试连接失败"""
        mock_get.side_effect = Exception("Connection error")
        assert loader.test_connection() is False

    # ---------- URL 解析 ----------

    @pytest.mark.parametrize(
        "url,expected_id",
        [
            ("https://test.atlassian.net/wiki/spaces/TEST/pages/123456789/Page+Title", "123456789"),
            ("https://test.atlassian.net/wiki/spaces/TEST/pages/987654321", "987654321"),
            ("123456789", "123456789"),
            ("https://test.atlassian.net/wiki/spaces/TEST/pages/111?pageId=222", "111"),  # /pages/111 优先匹配
        ],
    )
    def test_extract_page_id(self, loader, url, expected_id):
        """测试从不同 URL 格式提取页面 ID"""
        page_id = loader._extract_page_id(url)
        assert page_id == expected_id

    def test_extract_page_id_invalid(self, loader):
        """测试无效 URL"""
        page_id = loader._extract_page_id("https://invalid-url.com")
        assert page_id is None

    # ---------- 完整加载流程 ----------

    @patch.object(ConfluenceLoader, "_fetch_pages")
    @patch.object(ConfluenceLoader, "_parse_page")
    def test_load_full_flow(self, mock_parse, mock_fetch, loader):
        """测试完整加载流程"""
        mock_fetch.return_value = [
            {"id": "1", "title": "Page 1"},
            {"id": "2", "title": "Page 2"},
        ]
        mock_parse.return_value = {
            "doc_id": "CONFL_1",
            "content": "内容",
            "source_type": "test_case",
            "module": "TEST",
            "tags": ["测试"],
            "metadata": {},
        }

        docs = loader.load(space_key="TEST", max_results=10)

        assert len(docs) == 2
        assert mock_fetch.call_count == 1
        assert mock_parse.call_count == 2


# ============================================================================
# JiraLoader 测试
# ============================================================================

class TestJiraLoader:
    """JIRA 加载器测试"""

    @pytest.fixture
    def jira_config(self):
        """JIRA 配置"""
        return {
            "url": "https://test.atlassian.net",
            "email": "test@test.com",
            "api_token": "test-token",
            "project_key": "TEST",
        }

    @pytest.fixture
    def loader(self, jira_config):
        """JiraLoader 实例"""
        return JiraLoader(
            url=jira_config["url"],
            email=jira_config["email"],
            api_token=jira_config["api_token"],
            project_key=jira_config["project_key"],
        )

    def test_init(self, jira_config):
        """测试初始化"""
        loader = JiraLoader(
            url=jira_config["url"],
            email=jira_config["email"],
            api_token=jira_config["api_token"],
            project_key=jira_config["project_key"],
        )
        assert loader.url == "https://test.atlassian.net"
        assert loader.project_key == "TEST"

    def test_close_releases_session(self, loader):
        """测试 close() 释放连接"""
        loader.session.close = Mock()
        loader.close()
        loader.session.close.assert_called_once()

    # ---------- JQL 查询构建 ----------

    @patch("requests.Session.get")
    def test_fetch_issues_single_page(self, mock_get, loader):
        """测试单页获取 Issues"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": 2,
            "issues": [
                {"key": "TEST-1", "fields": {"summary": "Bug 1"}},
                {"key": "TEST-2", "fields": {"summary": "Bug 2"}},
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        issues = loader._fetch_issues(jql="issuetype = Bug", max_results=10)

        assert len(issues) == 2
        assert issues[0]["key"] == "TEST-1"

    @patch("requests.Session.get")
    def test_fetch_issues_api_error(self, mock_get, loader):
        """测试 API 错误"""
        mock_response = Mock()
        mock_response.raise_for_status = Mock(side_effect=Exception("API Error"))
        mock_get.return_value = mock_response

        with pytest.raises(Exception, match="API Error"):
            loader._fetch_issues(jql="issuetype = Bug", max_results=10)

    # ---------- Issue 解析 ----------

    def test_parse_issue_basic(self, loader):
        """测试解析基本 Issue"""
        issue = {
            "key": "TEST-123",
            "fields": {
                "summary": "支付功能异常",
                "description": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "用户无法完成支付"}
                            ]
                        }
                    ]
                },
                "labels": ["payment", "urgent"],
                "priority": {"name": "High"},
                "status": {"name": "Done"},
                "created": "2026-04-01T10:00:00.000+0000",
                "updated": "2026-04-10T10:00:00.000+0000",
                "assignee": {"displayName": "张三"},
                "components": [{"name": "支付模块"}],
            }
        }

        doc = loader._parse_issue(issue)

        assert doc is not None
        assert doc["doc_id"] == "JIRA_TEST-123"
        assert "支付功能异常" in doc["content"]
        assert doc["source_type"] == "bug_report"
        assert doc["module"] == "支付模块"
        assert "payment" in doc["tags"]
        assert "urgent" in doc["tags"]
        assert doc["metadata"]["priority"] == "P0"
        assert doc["metadata"]["status"] == "Done"
        assert doc["metadata"]["last_updated"] == "2026-04-10T10:00:00.000+0000"
        assert doc["metadata"]["jira_key"] == "TEST-123"

    def test_parse_issue_no_components(self, loader):
        """测试解析无组件的 Issue"""
        issue = {
            "key": "TEST-456",
            "fields": {
                "summary": "一般问题",
                "description": None,
                "labels": ["test"],
                "priority": {"name": "Medium"},
                "status": {"name": "Open"},
                "created": "2026-04-01T10:00:00.000+0000",
                "updated": "2026-04-05T10:00:00.000+0000",
                "assignee": None,
                "components": [],
            }
        }

        doc = loader._parse_issue(issue)

        assert doc is not None
        assert doc["module"] == "unknown"
        assert "test" in doc["tags"]

    def test_parse_issue_invalid(self, loader):
        """测试解析异常 Issue"""
        doc = loader._parse_issue(None)
        assert doc is None

    # ---------- 关键词提取 ----------

    def test_extract_keywords(self, loader):
        """测试关键词提取"""
        content = "标题：支付功能异常\n描述：用户无法完成支付\n状态：Done\n优先级：High"
        tags = loader._extract_keywords(content, top_k=5)

        assert isinstance(tags, list)
        assert len(tags) <= 5
        assert "支付" in tags

    # ---------- 便捷方法 ----------

    @patch.object(JiraLoader, "_fetch_issues")
    def test_load_bugs(self, mock_fetch, loader):
        """测试加载 Bug"""
        mock_fetch.return_value = [
            {"key": "BUG-1", "fields": {"summary": "Bug 1"}},
        ]

        docs = loader.load_bugs(status="Done", max_results=10)

        assert len(docs) == 1
        mock_fetch.assert_called_once_with("issuetype = Bug AND project = TEST AND status = Done ORDER BY created DESC", 10)

    @patch.object(JiraLoader, "_fetch_issues")
    def test_load_tasks(self, mock_fetch, loader):
        """测试加载 Task"""
        mock_fetch.return_value = []
        docs = loader.load_tasks(max_results=5)
        assert docs == []

    # ---------- 连接测试 ----------

    @patch("requests.Session.get")
    def test_test_connection_success(self, mock_get, loader):
        """测试连接成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"displayName": "Test User"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        assert loader.test_connection() is True

    @patch("requests.Session.get")
    def test_test_connection_failure(self, mock_get, loader):
        """测试连接失败"""
        mock_get.side_effect = Exception("Connection error")
        assert loader.test_connection() is False

    # ---------- 完整加载流程 ----------

    @patch.object(JiraLoader, "_fetch_issues")
    @patch.object(JiraLoader, "_parse_issue")
    def test_load_full_flow(self, mock_parse, mock_fetch, loader):
        """测试完整加载流程"""
        mock_fetch.return_value = [
            {"key": "TEST-1", "fields": {}},
            {"key": "TEST-2", "fields": {}},
        ]
        mock_parse.return_value = {
            "doc_id": "JIRA_TEST-1",
            "content": "内容",
            "source_type": "bug_report",
            "module": "支付模块",
            "tags": ["支付"],
            "metadata": {},
        }

        docs = loader.load(issue_type="Bug", max_results=10)

        assert len(docs) == 2
        assert mock_fetch.call_count == 1
        assert mock_parse.call_count == 2
