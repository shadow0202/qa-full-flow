"""JIRA数据加载器 - 从JIRA拉取缺陷和问题"""
import requests
from typing import List, Dict, Optional
from src.data_pipeline.loaders.base import BaseLoader


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
        
        print(f"🔗 JIRA连接器已初始化: {self.url}")
        if project_key:
            print(f"   项目: {project_key}")
    
    def load(self, source: str = "", 
             issue_type: str = "Bug",
             status: str = "",
             max_results: int = 100) -> List[Dict]:
        """
        从JIRA加载缺陷数据
        
        Args:
            source: 未使用（保持接口一致性）
            issue_type: 问题类型（Bug, Task, Story等）
            status: 状态过滤（Done, Closed等）
            max_results: 最大结果数
            
        Returns:
            文档列表
        """
        print(f"\n📥 正在从JIRA拉取 {issue_type} 数据...")
        
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
        
        print(f"✅ JIRA数据加载完成: {len(documents)} 条")
        return documents
    
    def load_bugs(self, status: str = "", max_results: int = 100) -> List[Dict]:
        """便捷方法：加载Bug"""
        return self.load(issue_type="Bug", status=status, max_results=max_results)
    
    def load_tasks(self, status: str = "", max_results: int = 100) -> List[Dict]:
        """便捷方法：加载Task"""
        return self.load(issue_type="Task", status=status, max_results=max_results)
    
    def _fetch_issues(self, jql: str, max_results: int) -> List[Dict]:
        """执行JQL查询"""
        url = f"{self.url}/rest/api/3/search"
        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,description,labels,components,priority,status,issuetype,created,updated,assignee"
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            total = data.get("total", 0)
            print(f"   查询到 {total} 条记录，返回 {len(data.get('issues', []))} 条")
            
            return data.get("issues", [])
        except Exception as e:
            raise Exception(f"JIRA API调用失败: {str(e)}")
    
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
                "tags": labels[:10],  # 限制标签数量
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
            print(f"⚠️  解析JIRA问题失败: {e}")
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
    
    def test_connection(self) -> bool:
        """测试连接是否正常"""
        try:
            url = f"{self.url}/rest/api/3/myself"
            response = self.session.get(url)
            response.raise_for_status()
            user = response.json()
            print(f"✅ JIRA连接成功: {user.get('displayName', 'Unknown')}")
            return True
        except Exception as e:
            print(f"❌ JIRA连接失败: {e}")
            return False
