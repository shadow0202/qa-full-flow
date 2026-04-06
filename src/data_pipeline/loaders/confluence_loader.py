"""Confluence数据加载器 - 从Confluence拉取文档和知识库"""
import requests
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from src.data_pipeline.loaders.base import BaseLoader


class ConfluenceLoader(BaseLoader):
    """Confluence文档数据加载器"""
    
    def __init__(self, url: str, email: str, api_token: str,
                 verify_ssl: bool = True):
        """
        初始化Confluence连接器
        
        Args:
            url: Confluence地址，如 https://your-company.atlassian.net/wiki
            email: 邮箱账号
            api_token: API Token
            verify_ssl: 是否验证SSL证书
        """
        self.url = url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.verify_ssl = verify_ssl
        
        # 设置认证
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        self.session.verify = verify_ssl
        
        print(f"🔗 Confluence连接器已初始化: {self.url}")
    
    def load(self, source: str = "",
             space_key: str = "",
             max_results: int = 50) -> List[Dict]:
        """
        从Confluence加载文档
        
        Args:
            source: 未使用（保持接口一致性）
            space_key: 空间Key（如"TEST"、"DEV"等）
            max_results: 最大结果数
            
        Returns:
            文档列表
        """
        print(f"\n📥 正在从Confluence拉取文档...")
        
        # 获取页面列表
        pages = self._fetch_pages(space_key, max_results)
        
        # 转换为标准格式
        documents = []
        for page in pages:
            doc = self._parse_page(page)
            if doc:
                documents.append(doc)
        
        print(f"✅ Confluence数据加载完成: {len(documents)} 条")
        return documents
    
    def load_space(self, space_key: str, max_results: int = 50) -> List[Dict]:
        """便捷方法：加载指定空间"""
        return self.load(space_key=space_key, max_results=max_results)
    
    def load_test_docs(self, max_results: int = 50) -> List[Dict]:
        """便捷方法：加载测试相关文档"""
        print("🔍 搜索测试相关文档...")
        pages = self._search_pages("测试", max_results)
        
        documents = []
        for page in pages:
            doc = self._parse_page(page)
            if doc:
                documents.append(doc)
        
        print(f"✅ 测试文档加载完成: {len(documents)} 条")
        return documents
    
    def _fetch_pages(self, space_key: str, max_results: int) -> List[Dict]:
        """获取页面列表"""
        url = f"{self.url}/rest/api/content"
        params = {
            "type": "page",
            "expand": "space,version,ancestors",
            "limit": max_results
        }
        
        if space_key:
            params["spaceKey"] = space_key
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            print(f"   查询到 {len(results)} 个页面")
            
            return results
        except Exception as e:
            raise Exception(f"Confluence API调用失败: {str(e)}")
    
    def _search_pages(self, query: str, max_results: int) -> List[Dict]:
        """搜索页面"""
        url = f"{self.url}/rest/api/content/search"
        params = {
            "cql": f"text ~ '{query}'",
            "expand": "space,version",
            "limit": max_results
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            print(f"   搜索到 {len(results)} 个页面")
            
            return results
        except Exception as e:
            print(f"⚠️  搜索失败: {e}，返回空列表")
            return []
    
    def _parse_page(self, page: Dict) -> Optional[Dict]:
        """
        解析Confluence页面为统一格式
        支持v1和v2 API的返回格式
        """
        try:
            # 检测是v1还是v2 API格式
            is_v2 = "id" in page and isinstance(page.get("id"), str) and not page.get("type")

            if is_v2:
                # v2 API格式
                page_id = page.get("id", "")
                title = page.get("title", "")
                space_id = page.get("spaceId", "")
                parent_id = page.get("parentId", "")
                version = page.get("version", {})
                version_number = version.get("number", 0)
                author_id = version.get("authorId", "")
                created_at = version.get("createdAt", "")
                updated_at = version.get("createdAt", "")  # v2 API 用 createdAt
            else:
                # v1 API格式
                page_id = page.get("id", "")
                title = page.get("title", "")
                space = page.get("space", {})
                space_id = space.get("key", "")
                parent_id = ""
                version = page.get("version", {})
                version_number = version.get("number", 0)
                author_id = version.get("by", {}).get("accountId", "")
                created_at = page.get("history", {}).get("createdDate", "")
                updated_at = version.get("when", "")  # v1 API 有 version.when

            # 获取页面内容
            content_body = self._get_page_body(page_id)
            if not content_body:
                return None

            # 构建内容（用于向量化）
            content = f"标题：{title}\n\n{content_body}"

            # 确定来源类型
            source_type = self._classify_page(title, content_body)

            return {
                "doc_id": f"CONFL_{page_id}",
                "content": content,
                "source_type": source_type,
                "module": space_id,
                "tags": [],  # v2 API需要额外请求labels
                "metadata": {
                    "priority": "P2",  # 文档默认P2
                    "version": f"v{version_number}",
                    "author": author_id,
                    "create_date": created_at[:10] if created_at else "",
                    "last_updated": updated_at,  # 新增：Confluence 更新时间
                    "space_key": space_id,
                    "space_name": space_id,
                    "page_title": title,
                    "url": f"{self.url}/spaces/{space_id}/pages/{page_id}" if is_v2 else f"{self.url}/spaces/{space.get('key', '')}/pages/{page_id}"
                }
            }
        except Exception as e:
            print(f"⚠️  解析Confluence页面失败: {e}")
            return None
    
    def _get_page_body(self, page_id: str) -> str:
        """
        获取页面正文（使用Confluence v2 API）
        
        v2 API端点: GET /wiki/api/v2/pages/{id}
        参数:
          - body-format: storage (原始存储格式，HTML)
          - status: current (当前版本)
        """
        # 使用 v2 API
        url = f"{self.url}/wiki/api/v2/pages/{page_id}"
        params = {
            "body-format": "storage",  # 返回原始HTML格式
            "status": "current"
        }

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # v2 API返回格式: {"body": {"storage": {"value": "<html>..."}}}
            body = data.get("body", {}).get("storage", {}).get("value", "")
            if not body:
                # 如果storage为空，尝试view格式
                body = data.get("body", {}).get("view", {}).get("value", "")
            
            if not body:
                return ""

            # HTML转文本
            text = self._html_to_text(body)
            return text
        except Exception as e:
            print(f"⚠️  获取页面内容失败: {e}")
            return ""
    
    def _html_to_text(self, html: str) -> str:
        """简化版HTML转文本"""
        try:
            # 使用BeautifulSoup解析（如果安装了bs4）
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            return text
        except ImportError:
            # 如果没有BeautifulSoup，简单去除标签
            import re
            text = re.sub(r'<[^>]+>', ' ', html)
            # 清理空白
            text = ' '.join(text.split())
            return text
        except Exception:
            return html
    
    def _classify_page(self, title: str, content: str) -> str:
        """根据标题和内容分类"""
        title_lower = title.lower()
        content_lower = content.lower()
        
        if any(kw in title_lower for kw in ["测试", "test", "用例", "case"]):
            return "test_case"
        elif any(kw in title_lower for kw in ["需求", "requirement", "prd"]):
            return "business_rule"
        elif any(kw in title_lower for kw in ["bug", "缺陷", "问题"]):
            return "bug_report"
        else:
            return "business_rule"  # 默认归类为业务规则
    
    def test_connection(self) -> bool:
        """测试连接是否正常（使用v2 API）"""
        try:
            # v2 API: GET /wiki/api/v2/pages
            url = f"{self.url}/wiki/api/v2/pages"
            params = {"limit": 1}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            pages = data.get("results", [])
            print(f"✅ Confluence连接成功（v2 API），可用页面数: {len(pages)}")
            if pages:
                print(f"   示例页面: {pages[0].get('title', '')}")
            return True
        except Exception as e:
            print(f"❌ Confluence连接失败: {e}")
            return False

    def load_from_url(self, url: str) -> Optional[Dict]:
        """
        通过Confluence页面URL获取页面内容
        
        Args:
            url: Confluence页面完整URL或页面ID
            
        Returns:
            解析后的文档字典，失败返回None
        """
        try:
            # 从URL中提取页面ID
            page_id = self._extract_page_id(url)
            if not page_id:
                print(f"⚠️  无法从URL提取页面ID: {url}")
                return None
            
            print(f"📥 正在从URL获取Confluence页面: {url}")
            
            # 获取页面内容
            page_body = self._get_page_body(page_id)
            if not page_body:
                print(f"⚠️  无法获取页面内容: {url}")
                return None
            
            # 获取页面元数据
            page_meta = self._get_page_metadata(page_id)
            if not page_meta:
                print(f"⚠️  无法获取页面元数据: {url}")
                return None
            
            # 构建文档
            doc = self._parse_page(page_meta)
            if doc:
                # 覆盖URL为用户提供的原始URL
                doc["metadata"]["original_url"] = url
                print(f"✅ 成功获取页面: {doc.get('metadata', {}).get('page_title', '')}")
            
            return doc
            
        except Exception as e:
            print(f"❌ 从URL加载Confluence页面失败: {e}")
            return None

    def load_from_urls(self, urls: List[str]) -> List[Dict]:
        """
        批量通过URL获取多个Confluence页面
        
        Args:
            urls: Confluence页面URL列表
            
        Returns:
            解析后的文档列表
        """
        if not urls:
            return []
        
        print(f"\n📥 正在批量获取 {len(urls)} 个Confluence页面...")
        
        documents = []
        success_count = 0
        fail_count = 0
        
        for i, url in enumerate(urls, 1):
            print(f"  [{i}/{len(urls)}] 处理: {url}")
            doc = self.load_from_url(url)
            if doc:
                documents.append(doc)
                success_count += 1
            else:
                fail_count += 1
        
        print(f"\n✅ 批量获取完成: 成功 {success_count} 个，失败 {fail_count} 个")
        return documents

    def _extract_page_id(self, url: str) -> Optional[str]:
        """
        从Confluence URL中提取页面ID
        
        支持的URL格式:
        - https://xxx.atlassian.net/wiki/spaces/XXX/pages/123456789/Page+Title
        - https://xxx.atlassian.net/wiki/spaces/XXX/pages/123456789
        - 直接传入页面ID: 123456789
        """
        # 如果直接是数字ID
        if url.strip().isdigit():
            return url.strip()
        
        try:
            # 尝试从URL路径中提取
            # 格式: /spaces/XXX/pages/PAGE_ID
            import re
            patterns = [
                r'/pages/(\d+)',  # /pages/123456789
                r'/pages/\d+/[^/]+-(\d+)',  # /pages/123456789-Title (某些格式)
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            
            # 如果URL包含pageId参数
            match = re.search(r'[?&]pageId=(\d+)', url)
            if match:
                return match.group(1)
                
            return None
            
        except Exception as e:
            print(f"⚠️  提取页面ID失败: {e}")
            return None

    def _get_page_metadata(self, page_id: str) -> Optional[Dict]:
        """
        获取页面元数据（使用Confluence v2 API）
        
        v2 API会返回更简洁的元数据结构
        """
        url = f"{self.url}/wiki/api/v2/pages/{page_id}"
        params = {
            "status": "current",
            # v2 API使用include-*参数而不是expand
            "include-versions": True,  # 包含版本信息
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"⚠️  获取页面元数据失败: {e}")
            return None
