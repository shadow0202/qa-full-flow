"""Tapd数据加载器 - 从Tapd拉取Bug、需求/文档、测试用例"""
import requests
import logging
import re
import html
import jieba.analyse
from typing import List, Dict, Optional
from src.qa_full_flow.data_pipeline.loaders.base import BaseLoader

logger = logging.getLogger(__name__)


class TapdLoader(BaseLoader):
    """Tapd数据加载器"""

    BASE_URL = "https://api.tapd.cn"
    
    # 优先级映射（统一常量）
    _PRIORITY_MAP = {
        "Critical": "P0", "High": "P1", "Medium": "P2", "Low": "P3",
        "紧急": "P0", "高": "P1", "中": "P2", "低": "P3"
    }

    def __init__(self, workspace_id: str, api_user: str, api_password: str, verify_ssl: bool = True):
        """
        初始化Tapd连接器 (使用 HTTP Basic Authentication)

        Args:
            workspace_id: Tapd 项目 workspace_id
            api_user: Tapd API 用户名
            api_password: Tapd API 口令
            verify_ssl: 是否验证SSL证书
        """
        self.workspace_id = workspace_id
        self.api_user = api_user
        self.api_password = api_password
        self.verify_ssl = verify_ssl

        # 设置认证 Session (使用 HTTP Basic Auth)
        self.session = requests.Session()
        self.session.auth = (api_user, api_password)
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.session.verify = verify_ssl

        logger.info(f"Tapd连接器已初始化: Workspace {workspace_id}")

    @staticmethod
    def _clean_html(raw_text: str) -> str:
        """
        清理 HTML 标签，保留纯文本和换行
        适用于 Bug 描述和 Testcase 内容
        不处理 Markdown 标题
        """
        if not raw_text:
            return ""

        text = raw_text

        # 0. 移除 script 和 style 标签及其内容
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)

        # 1. 保留换行符：将 <br>, <br/>, <br />, <p> 替换为换行符
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)

        # 2. 表格行处理
        text = re.sub(r'<tr[^>]*>', '\n', text, flags=re.IGNORECASE)
        
        # 3. 移除剩余的 HTML 标签
        text = re.sub(r'<[^>]+>', '', text)

        # 4. 处理 HTML 实体 (如 &gt;, &nbsp;, &amp;)
        text = html.unescape(text)

        # 5. 将 \xa0 (nbsp) 替换为普通空格
        text = text.replace('\xa0', ' ')

        # 6. 清理多余空白：将 3 个以上的换行减少为 2 个
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 7. 去除首尾空白
        return text.strip()

    def load(self, source: str = "", **kwargs) -> List[Dict]:
        """
        从Tapd加载数据

        Args:
            source: 未使用（保持接口一致性），或者用作 workspace_id 备用
            **kwargs: 加载器特定参数
                - resource_type: 资源类型 (bugs, stories, testcases, wikis)，默认"bugs"
                - max_results: 最大结果数，默认100
                - last_updated: 增量更新时间 (ISO 8601 格式)

        Returns:
            文档列表
        """
        resource_type = kwargs.get("resource_type", "bugs")
        max_results = kwargs.get("max_results", 100)
        last_updated = kwargs.get("last_updated", None)
        workspace = source or self.workspace_id
        logger.info(f"正在从Tapd拉取 {resource_type} 数据... (Workspace: {workspace})")

        # 映射资源到对应的解析方法
        parse_method_map = {
            "bugs": self._parse_bug,
            "stories": self._parse_story,
            "testcases": self._parse_testcase,
            "wikis": self._parse_wiki,
        }

        if resource_type not in parse_method_map:
            raise ValueError(f"Unsupported resource_type: {resource_type}. Use 'bugs', 'stories', 'testcases', or 'wikis'.")

        parse_func = parse_method_map[resource_type]

        # 拉取数据
        items = self._fetch_items(workspace, resource_type, max_results, last_updated)

        # Wiki 批量 API 不返回完整内容，需要单独获取
        if resource_type == "wikis":
            logger.info(f"正在获取 {len(items)} 条 Wiki 的完整内容...")
            full_wikis = []
            for item in items:
                wiki = item.get("Wiki", {})
                wiki_id = wiki.get("id")
                if wiki_id:
                    full_wiki_doc = self.get_wiki_by_id(wiki_id)
                    if full_wiki_doc:
                        full_wikis.append(full_wiki_doc)
            
            logger.info(f"成功获取 {len(full_wikis)} 条完整 Wiki")
            return full_wikis

        # 转换为标准格式
        documents = []
        for item in items:
            doc = parse_func(item)
            if doc:
                documents.append(doc)

        logger.info(f"Tapd {resource_type} 数据加载完成: {len(documents)} 条")
        return documents

    def _fetch_items(self, workspace_id: str, resource: str, max_results: int, last_updated: Optional[str] = None) -> List[Dict]:
        """
        通用数据拉取方法 (支持分页) - 用于批量拉取数据
        """
        # Testcase API 使用不同的端点
        if resource == "testcases":
            resource = "tcases"
        
        url = f"{self.BASE_URL}/{resource}"
        all_items = []
        page = 1
        limit = min(max_results, 200)  # Tapd 单次最大 200

        while len(all_items) < max_results:
            params = {
                "workspace_id": workspace_id,
                "limit": limit,
                "page": page
            }

            # 增量更新过滤
            if last_updated:
                # Tapd API 过滤语法: modified[>=]=YYYY-MM-DD
                # 简化处理，截取日期部分
                date_part = last_updated[:10]
                params["modified[>=]"] = date_part

            try:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("status") != 1:
                    logger.error(f"Tapd API Error: {data.get('info', 'Unknown error')}")
                    break

                items = data.get("data", [])
                if not items:
                    break

                all_items.extend(items)
                logger.debug(f"分页拉取: Page {page}, Count {len(items)}, Total {len(all_items)}")

                if len(items) < limit:
                    break

                page += 1

            except Exception as e:
                raise RuntimeError(f"Tapd API调用失败: {str(e)}") from e

        return all_items[:max_results]

    def get_wiki_by_id(self, wiki_id: str) -> Optional[Dict]:
        """
        通过 Wiki ID 获取单个 Wiki 详情
        """
        try:
            url = f"{self.BASE_URL}/tapd_wikis"
            params = {
                "workspace_id": self.workspace_id,
                "id": wiki_id
            }

            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != 1:
                logger.error(f"获取 Wiki 失败: {data.get('info', 'Unknown error')}")
                return None

            items = data.get("data", [])
            if not items:
                logger.warning(f"未找到 Wiki: {wiki_id}")
                return None

            # 解析并返回
            return self._parse_wiki(items[0])

        except Exception as e:
            logger.error(f"获取 Wiki 异常: {e}")
            return None

    # ---------- 数据解析 ----------

    def _parse_bug(self, item: Dict) -> Optional[Dict]:
        """解析 Tapd Bug"""
        try:
            # Tapd API 返回格式: {"Bug": {...}}
            bug = item.get("Bug", {})
            bug_id = bug.get("id", "")
            title = bug.get("title", "无标题")
            # 清理 HTML 标签
            description = self._clean_html(bug.get("description", ""))
            status = bug.get("status", "")
            priority = bug.get("priority_label", bug.get("priority", ""))
            severity = bug.get("severity", "")
            created = bug.get("created", "")
            modified = bug.get("modified", "")
            reporter = bug.get("reporter", "")
            owner = bug.get("current_owner", "")

            content = f"标题：{title}\n描述：{description}\n状态：{status}\n严重程度：{severity}"

            # 提取关键词
            tags = self._extract_keywords(content, top_k=10)

            # 优先级映射
            mapped_priority = self._PRIORITY_MAP.get(priority, "P2")

            return {
                "doc_id": f"TAPD_BUG_{bug_id}",
                "content": content,
                "source_type": "bug",
                "module": bug.get("custom_field_one", "默认模块"),
                "tags": tags,
                "metadata": {
                    "priority": mapped_priority,
                    "severity": severity,
                    "version": "",
                    "author": reporter,
                    "owner": owner,
                    "create_date": created[:10] if created else "",
                    "last_updated": modified,
                    "tapd_id": bug_id,
                    "status": status,
                    "url": f"https://www.tapd.cn/tapd_fe/{self.workspace_id}/bug/detail/{bug_id}"
                }
            }
        except Exception as e:
            logger.warning(f"解析 Tapd Bug 失败: {e}")
            return None

    def _parse_story(self, item: Dict) -> Optional[Dict]:
        """解析 Tapd Story (需求/文档)"""
        try:
            story = item.get("Story", {})
            story_id = story.get("id", "")
            name = story.get("name", "无标题")
            description = story.get("description", "")
            status = story.get("status", "")
            created = story.get("created", "")
            modified = story.get("modified", "")
            creator = story.get("creator", "")
            priority = story.get("priority_label", story.get("priority", ""))

            content = f"标题：{name}\n描述：{description}\n状态：{status}"

            # 提取关键词
            tags = self._extract_keywords(content, top_k=10)

            # 优先级映射
            mapped_priority = self._PRIORITY_MAP.get(priority, "P2")

            return {
                "doc_id": f"TAPD_STORY_{story_id}",
                "content": content,
                "source_type": "story",
                "module": "需求池",
                "tags": tags,
                "metadata": {
                    "priority": mapped_priority,
                    "version": "",
                    "author": creator,
                    "create_date": created[:10] if created else "",
                    "last_updated": modified,
                    "tapd_id": story_id,
                    "status": status,
                    "url": f"https://www.tapd.cn/tapd_fe/{self.workspace_id}/story/detail/{story_id}"
                }
            }
        except Exception as e:
            logger.warning(f"解析 Tapd Story 失败: {e}")
            return None

    def _parse_testcase(self, item: Dict) -> Optional[Dict]:
        """解析 Tapd Testcase"""
        try:
            # 防御性检查：如果 item 不是字典，尝试获取 Tcase 键
            if not isinstance(item, dict):
                logger.warning(f"Testcase item 格式不正确: {type(item)}")
                return None
            
            tc = item.get("Tcase", {})
            if not isinstance(tc, dict):
                logger.warning(f"Tcase 字段格式不正确: {type(tc)}")
                return None
            
            tc_id = tc.get("id", "")
            name = tc.get("name", "无标题")
            # 清理 HTML 标签
            precondition = self._clean_html(tc.get("precondition", ""))
            steps = self._clean_html(tc.get("steps", ""))
            expectation = self._clean_html(tc.get("expectation", ""))
            
            created = tc.get("created", "")
            modified = tc.get("modified", "")
            creator = tc.get("creator", "")
            tc_type = tc.get("type", "")
            priority = tc.get("priority", "")
            status = tc.get("status", "")

            content = f"标题：{name}\n前置条件：{precondition}\n步骤：{steps}\n预期结果：{expectation}"

            # 提取关键词
            tags = self._extract_keywords(content, top_k=10)

            # 优先级映射
            priority_map = {"高": "P0", "中": "P2", "低": "P3"}
            mapped_priority = priority_map.get(priority, "P2")

            return {
                "doc_id": f"TAPD_TC_{tc_id}",
                "content": content,
                "source_type": "testcase",
                "module": "测试用例库",
                "tags": tags,
                "metadata": {
                    "priority": mapped_priority,
                    "version": "",
                    "author": creator,
                    "create_date": created[:10] if created else "",
                    "last_updated": modified,
                    "tapd_id": tc_id,
                    "status": status,
                    "type": tc_type,
                    "url": f"https://www.tapd.cn/tapd_fe/{self.workspace_id}/testcase/detail/{tc_id}"
                }
            }
        except Exception as e:
            logger.warning(f"解析 Tapd Testcase 失败: {e}")
            return None

    def _parse_wiki(self, item: Dict) -> Optional[Dict]:
        """解析 Tapd Wiki（知识库文档）"""
        try:
            wiki = item.get("Wiki", {})
            wiki_id = wiki.get("id", "")
            name = wiki.get("name", "无标题")
            # Wiki 内容优先使用 Markdown 格式
            description = wiki.get("markdown_description", wiki.get("description", ""))
            creator = wiki.get("creator", "")
            modifier = wiki.get("modifier", "")
            created = wiki.get("created", "")
            modified = wiki.get("modified", "")
            parent_wiki_id = wiki.get("parent_wiki_id", "")
            note = wiki.get("note", "")
            view_count = wiki.get("view_count", "0")

            # 构建完整内容
            content_parts = [f"标题：{name}"]
            if note:
                content_parts.append(f"备注：{note}")
            if description:
                content_parts.append(f"内容：{description}")
            
            content = "\n".join(content_parts)

            # 提取关键词
            tags = self._extract_keywords(content, top_k=10)

            # 构建 URL
            url = f"https://www.tapd.cn/tapd_fe/{self.workspace_id}/wiki/view/{wiki_id}"
            if parent_wiki_id and parent_wiki_id != "0":
                url = f"https://www.tapd.cn/tapd_fe/{self.workspace_id}/wiki/view/{parent_wiki_id}/{wiki_id}"

            return {
                "doc_id": f"TAPD_WIKI_{wiki_id}",
                "content": content,
                "source_type": "wiki",
                "module": "Wiki知识库",
                "tags": tags,
                "metadata": {
                    "priority": "P2",
                    "version": "",
                    "author": creator,
                    "modifier": modifier,
                    "create_date": created[:10] if created else "",
                    "last_updated": modified,
                    "tapd_id": wiki_id,
                    "parent_wiki_id": parent_wiki_id,
                    "view_count": view_count,
                    "note": note,
                    "url": url
                }
            }
        except Exception as e:
            logger.warning(f"解析 Tapd Wiki 失败: {e}")
            return None

    def _extract_keywords(self, content: str, top_k: int = 10) -> List[str]:
        """从文档内容中提取关键词"""
        try:
            keywords = jieba.analyse.extract_tags(content, topK=top_k, withWeight=False)
            return keywords
        except Exception as e:
            logger.warning(f"关键词提取失败: {e}")
            return []

    def test_connection(self) -> bool:
        """测试连接是否正常"""
        try:
            # 尝试获取 1 个 Bug 验证连接
            url = f"{self.BASE_URL}/bugs"
            params = {"workspace_id": self.workspace_id, "limit": 1}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == 1:
                logger.info(f"Tapd 连接成功: Workspace {self.workspace_id}")
                return True
            else:
                logger.error(f"Tapd 连接失败: {data.get('info')}")
                return False
        except Exception as e:
            logger.error(f"Tapd 连接异常: {e}")
            return False
