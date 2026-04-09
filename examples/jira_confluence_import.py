"""JIRA和Confluence数据加载示例"""
import sys
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent))

from src.qa_full_flow.core.config import settings
from src.qa_full_flow.embedding.embedder import Embedder
from src.qa_full_flow.vector_store.chroma_store import ChromaStore
from src.qa_full_flow.retrieval.retriever import Retriever
from src.qa_full_flow.data_pipeline.pipeline import DataPipeline
from src.qa_full_flow.data_pipeline.loaders.jira_loader import JiraLoader
from src.qa_full_flow.data_pipeline.loaders.confluence_loader import ConfluenceLoader


def example_jira_import():
    """示例1：从JIRA导入缺陷数据"""
    print("="*60)
    print("📥 示例1：从JIRA导入缺陷数据")
    print("="*60)
    
    # 检查配置
    if not settings.JIRA_API_TOKEN:
        print("⚠️  未配置JIRA API Token，跳过此示例")
        print("   请在.env文件中配置JIRA相关参数")
        return
    
    # 初始化连接器
    jira = JiraLoader(
        url=settings.JIRA_URL,
        email=settings.JIRA_EMAIL,
        api_token=settings.JIRA_API_TOKEN,
        project_key=settings.JIRA_PROJECT_KEY
    )
    
    # 测试连接
    if not jira.test_connection():
        print("❌ JIRA连接失败")
        return
    
    # 初始化向量库
    embedder = Embedder()
    vector_store = ChromaStore()
    pipeline = DataPipeline(embedder, vector_store)
    
    # 导入Bug数据
    stats = pipeline.ingest(
        loader=jira,
        source="",  # JIRA不需要source参数
        skip_existing=True
    )
    
    print(f"\n✅ JIRA数据入库完成: {stats}")


def example_confluence_import():
    """示例2：从Confluence导入文档"""
    print("\n" + "="*60)
    print("📥 示例2：从Confluence导入文档")
    print("="*60)
    
    # 检查配置
    if not settings.CONFLUENCE_API_TOKEN:
        print("⚠️  未配置Confluence API Token，跳过此示例")
        print("   请在.env文件中配置Confluence相关参数")
        return
    
    # 初始化连接器
    confluence = ConfluenceLoader(
        url=settings.CONFLUENCE_URL,
        email=settings.CONFLUENCE_EMAIL,
        api_token=settings.CONFLUENCE_API_TOKEN
    )
    
    # 测试连接
    if not confluence.test_connection():
        print("❌ Confluence连接失败")
        return
    
    # 初始化向量库
    embedder = Embedder()
    vector_store = ChromaStore()
    pipeline = DataPipeline(embedder, vector_store)
    
    # 导入文档（指定空间Key，如"TEST"）
    # 如果需要导入所有空间，可以不传space_key
    stats = pipeline.ingest(
        loader=confluence,
        source="",  # Confluence不需要source参数
        skip_existing=True
    )
    
    print(f"\n✅ Confluence数据入库完成: {stats}")


def example_custom_import():
    """示例3：自定义导入（指定条件和过滤）"""
    print("\n" + "="*60)
    print("📥 示例3：自定义导入")
    print("="*60)
    
    if not settings.JIRA_API_TOKEN:
        print("⚠️  未配置JIRA API Token，跳过此示例")
        return
    
    # 初始化连接器
    jira = JiraLoader(
        url=settings.JIRA_URL,
        email=settings.JIRA_EMAIL,
        api_token=settings.JIRA_API_TOKEN,
        project_key=settings.JIRA_PROJECT_KEY
    )
    
    # 初始化向量库
    embedder = Embedder()
    vector_store = ChromaStore()
    pipeline = DataPipeline(embedder, vector_store)
    
    # 只导入已完成的Bug
    print("\n📋 导入已完成的Bug...")
    stats = pipeline.ingest(
        loader=jira,
        source="",
        skip_existing=True
    )
    # 注意：需要在JiraLoader.load()中传入status="Done"
    # 这里需要修改调用方式，示例代码如下：
    # bugs = jira.load_bugs(status="Done", max_results=200)
    # pipeline.ingest_data(bugs, skip_existing=True)
    
    print(f"\n✅ 自定义导入完成: {stats}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 JIRA & Confluence 数据导入示例")
    print("="*60 + "\n")
    
    # 运行示例
    example_jira_import()
    example_confluence_import()
    example_custom_import()
    
    print("\n" + "="*60)
    print("✅ 所有示例执行完成")
    print("="*60)
