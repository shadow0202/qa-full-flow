"""主入口 - 命令行工具"""
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config import settings
from src.embedding.embedder import Embedder
from src.vector_store.chroma_store import ChromaStore
from src.retrieval.retriever import Retriever
from src.data_pipeline.pipeline import DataPipeline
from src.data_pipeline.loaders.jsonl_loader import JSONLLoader


def main():
    """主函数"""
    print("="*60)
    print("🚀 AI测试用例与知识库系统")
    print("="*60)
    
    # 初始化服务
    print("\n📥 正在初始化...")
    embedder = Embedder()
    vector_store = ChromaStore()
    retriever = Retriever(embedder, vector_store)
    pipeline = DataPipeline(embedder, vector_store)
    
    # 检查是否有mock数据
    jsonl_path = Path("mock_test_data.jsonl")
    if jsonl_path.exists():
        print(f"\n📂 发现Mock数据: {jsonl_path}")
        loader = JSONLLoader()
        stats = pipeline.ingest(loader, str(jsonl_path), skip_existing=True)
        print(f"\n📊 入库统计: {stats}")
    
    # 测试检索
    print("\n" + "="*60)
    print("🔍 测试检索功能")
    print("="*60)
    
    test_queries = [
        ("支付成功后库存没扣减怎么办？", {"module": "订单支付"}),
        ("退款金额怎么算？优惠券退吗？", None)
    ]
    
    for query, filters in test_queries:
        print(f"\n[查询] {query}")
        if filters:
            print(f"  过滤条件: {filters}")
        
        results = retriever.search(query, n_results=2, filters=filters)
        
        for r in results:
            meta = r["metadata"]
            print(f"  ├─ [{meta.get('source_type', 'unknown')}] 相似度: {r.get('similarity', 0):.3f}")
            print(f"     {r['content'][:80]}...")
    
    print("\n" + "="*60)
    print("✅ 系统测试完成！")
    print("="*60)
    print(f"\n💾 知识库位置: {settings.VECTOR_DB_DIR}")
    print(f"📝 下次运行将自动跳过已入库数据")
    
    # 启动提示
    print("\n" + "="*60)
    print("🌐 启动API服务: uvicorn src.api.app:app --reload --port 8000")
    print("="*60)


if __name__ == "__main__":
    main()
