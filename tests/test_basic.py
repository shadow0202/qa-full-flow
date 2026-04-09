"""基础功能测试"""
import sys
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.qa_full_flow.core.config import settings
from src.qa_full_flow.embedding.embedder import Embedder
from src.qa_full_flow.vector_store.chroma_store import ChromaStore
from src.qa_full_flow.retrieval.retriever import Retriever
from src.qa_full_flow.data_pipeline.pipeline import DataPipeline
from src.qa_full_flow.data_pipeline.loaders.jsonl_loader import JSONLLoader


def test_config():
    """测试配置加载"""
    print("✅ 测试1: 配置加载")
    assert settings.root_dir.exists()
    assert settings.data_dir.exists()
    print(f"   根目录: {settings.root_dir}")
    print(f"   数据目录: {settings.data_dir}")


def test_embedder():
    """测试Embedding服务"""
    print("\n✅ 测试2: Embedding服务")
    embedder = Embedder()
    
    # 测试单文本编码
    vec = embedder.encode_single("测试文本")
    assert len(vec) > 0
    print(f"   向量维度: {len(vec)}")
    
    # 测试批量编码
    vecs = embedder.encode(["文本1", "文本2"])
    assert len(vecs) == 2
    print(f"   批量编码: 2条")


def test_chroma_store():
    """测试ChromaDB存储"""
    print("\n✅ 测试3: ChromaDB存储")
    store = ChromaStore()
    info = store.get_collection_info()
    print(f"   集合: {info['name']}")
    print(f"   文档数: {info['count']}")


def test_pipeline():
    """测试数据管道"""
    print("\n✅ 测试4: 数据管道")
    
    embedder = Embedder()
    store = ChromaStore()
    pipeline = DataPipeline(embedder, store)
    loader = JSONLLoader()
    
    # 检查mock数据
    jsonl_path = Path("test_knowledge/mock_test_data.jsonl")
    if jsonl_path.exists():
        stats = pipeline.ingest(loader, str(jsonl_path), skip_existing=True)
        print(f"   入库统计: {stats}")
    else:
        print("   ⚠️  Mock数据不存在，跳过")


def test_retrieval():
    """测试检索功能"""
    print("\n✅ 测试5: 检索功能")
    
    embedder = Embedder()
    store = ChromaStore()
    retriever = Retriever(embedder, store)
    
    # 测试查询
    results = retriever.search("支付", n_results=2)
    print(f"   查询'支付': 返回 {len(results)} 条结果")
    
    if results:
        print(f"   最佳匹配相似度: {results[0].get('similarity', 0):.3f}")


def test_api_schemas():
    """测试API数据模型"""
    print("\n✅ 测试6: API数据模型")

    from src.qa_full_flow.api.schemas import SearchRequest, SearchResponse
    
    req = SearchRequest(query="测试", n_results=5)
    assert req.query == "测试"
    assert req.n_results == 5
    print("   SearchRequest: OK")
    
    resp = SearchResponse(success=True, query="测试", results=[], total=0)
    assert resp.success is True
    print("   SearchResponse: OK")


if __name__ == "__main__":
    print("="*60)
    print("🧪 开始运行测试")
    print("="*60)
    
    test_config()
    test_embedder()
    test_chroma_store()
    test_pipeline()
    test_retrieval()
    test_api_schemas()
    
    print("\n" + "="*60)
    print("✅ 所有测试通过！")
    print("="*60)
