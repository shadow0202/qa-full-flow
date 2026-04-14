"""JIRA数据加载器 - 从JIRA拉取缺陷和问题"""
import requests
import logging
import jieba.analyse
from typing import List, Dict, Optional
from src.qa_full_flow.data_pipeline.loaders.base import BaseLoader

logger = logging.getLogger(__name__)


class JiraLoader(BaseLoader):
    """JIRA缺陷数据加载器"""
    
    def __init__(self, url: str, email: str, api_token: str, 
                 project_key: str = "", verify_ssl: bool = True):
        """
        初始化JIRA连接器
        
        Args:
            url: JIRA地址，如 https://your-company.atlassian.net
            email: 邮箱账号
            api_token: API Token
            project_key: 项目Key（可选，为空则拉取所有项目）
            verify_ssl: 是否验证SSL证书
        """
        self.url = url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.project_key = project_key
        self.verify_ssl = verify_ssl
        
        # 设置认证
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        self.session.verify = verify_ssl

        logger.info(f"JIRA连接器已初始化: {self.url}")
        if project_key:
            logger.info(f"项目: {project_key}")

    def close(self):
        """关闭 Session，释放连接资源"""
        if hasattr(self, 'session'):
            self.session.close()

    def __del__(self):
        """析构函数，确保连接被关闭"""
        self.close()
    
    def load(self, source: str = "", **kwargs) -> List[Dict]:
        """
        从JIRA加载缺陷数据

        Args:
            source: 未使用（保持接口一致性）
            **kwargs: 加载器特定参数
                - issue_type: 问题类型（Bug, Task, Story等），默认"Bug"
                - status: 状态过滤（Done, Closed等）
                - max_results: 最大结果数，默认100

        Returns:
            文档列表
        """
        issue_type = kwargs.get("issue_type", "Bug")
        status = kwargs.get("status", "")
        max_results = kwargs.get("max_results", 100)
        logger.info(f"正在从JIRA拉取 {issue_type} 数据...")

        # 构建JQL查询
        jql = f"issuetype = {issue_type}"
        if self.project_key:
            jql += f" AND project = {self.project_key}"
        if status:
            jql += f" AND status = {status}"
        jql += " ORDER BY created DESC"

        # 拉取数据
        issues = self._fetch_issues(jql, max_results)

        # 转换为标准格式
        documents = []
        for issue in issues:
            doc = self._parse_issue(issue)
            if doc:
                documents.append(doc)

        logger.info(f"JIRA数据加载完成: {len(documents)} 条")
        return documents
    
    def load_bugs(self, status: str = "", max_results: int = 100) -> List[Dict]:
        """便捷方法：加载Bug"""
        return self.load(issue_type="Bug", status=status, max_results=max_results)
    
    def load_tasks(self, status: str = "", max_results: int = 100) -> List[Dict]:
        """便捷方法：加载Task"""
        return self.load(issue_type="Task", status=status, max_results=max_results)
    
    def _fetch_issues(self, jql: str, max_results: int) -> List[Dict]:
        """执行JQL查询（支持分页）"""
        url = f"{self.url}/rest/api/3/search"
        all_issues = []
        start_at = 0
        page_size = min(max_results, 100)  # JIRA API 单次最大 100

        while start_at < max_results:
            params = {
                "jql": jql,
                "maxResults": page_size,
                "startAt": start_at,
                "fields": "summary,description,labels,components,priority,status,issuetype,created,updated,assignee"
            }

            try:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                total = data.get("total", 0)
                issues = data.get("issues", [])
                all_issues.extend(issues)

                logger.debug(f"分页拉取: {start_at}-{start_at+len(issues)} / 总计 {total} 条")

                if len(issues) < page_size:
                    break  # 没有更多数据了
                
                start_at += page_size

                if len(all_issues) >= max_results:
                    break  # 已达到用户请求的最大值

            except Exception as e:
                raise Exception(f"JIRA API调用失败: {str(e)}")

        logger.info(f"查询到 {len(all_issues)} 条记录（分页拉取完成）")
        return all_issues[:max_results]
    
    def _parse_issue(self, issue: Dict) -> Optional[Dict]:
        """解析JIRA问题为统一格式"""
        try:
            fields = issue.get("fields", {})
            key = issue.get("key", "")
            
            # 提取字段
            summary = fields.get("summary", "")
            description = self._extract_description(fields.get("description", {}))
            labels = fields.get("labels", [])
            priority = fields.get("priority", {}).get("name", "Medium")
            status = fields.get("status", {}).get("name", "")
            created = fields.get("created", "")
            updated = fields.get("updated", "")  # 新增：更新时间
            assignee = fields.get("assignee", {})
            assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
            
            # 构建内容（用于向量化）
            content = f"标题：{summary}\n"
            if description:
                content += f"描述：{description}\n"
            content += f"状态：{status}\n"
            content += f"优先级：{priority}\n"
            content += f"经办人：{assignee_name}"
            
            # 提取模块（从components或labels）
            components = fields.get("components", [])
            module = components[0].get("name", "unknown") if components else "unknown"

            # 自动提取关键词作为 tags（TF-IDF 算法）
            auto_tags = self._extract_keywords(content, top_k=10)
            # 合并 JIRA 原有标签和自动提取的标签
            tags = list(dict.fromkeys(labels[:5] + auto_tags))  # 去重，保留顺序

            # 映射优先级
            priority_map = {
                "Highest": "P0",
                "High": "P0",
                "Medium": "P1",
                "Low": "P2",
                "Lowest": "P3"
            }

            return {
                "doc_id": f"JIRA_{key}",
                "content": content,
                "source_type": "bug_report",
                "module": module,
                "tags": tags,  # 合并后的标签
                "metadata": {
                    "priority": priority_map.get(priority, "P2"),
                    "version": "",
                    "author": assignee_name,
                    "create_date": created[:10] if created else "",
                    "last_updated": updated,  # 新增：JIRA 更新时间
                    "jira_key": key,
                    "status": status,
                    "url": f"{self.url}/browse/{key}"
                }
            }
        except Exception as e:
            logger.warning(f"解析JIRA问题失败: {e}")
            return None
    
    def _extract_description(self, description: Dict) -> str:
        """提取JIRA描述文本（简化版，处理Atlassian Document Format）"""
        if not description:
            return ""

        # 简化处理：如果是纯文本直接返回
        if isinstance(description, str):
            return description

        # 处理ADF格式
        try:
            texts = []
            content = description.get("content", [])
            for block in content:
                if block.get("type") == "paragraph":
                    for inner in block.get("content", []):
                        if inner.get("type") == "text":
                            texts.append(inner.get("text", ""))
            return " ".join(texts)
        except Exception:
            return str(description)

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
    
    def test_connection(self) -> bool:
        """测试连接是否正常"""
        try:
            url = f"{self.url}/rest/api/3/myself"
            response = self.session.get(url)
            response.raise_for_status()
            user = response.json()
            logger.info(f"JIRA连接成功: {user.get('displayName', 'Unknown')}")
            return True
        except Exception as e:
            logger.error(f"JIRA连接失败: {e}")
            return False
