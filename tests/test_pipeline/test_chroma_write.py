"""ChromaDB 写入测试脚本

测试完整的数据入库流程：
1. 从 TAPD 获取数据
2. 执行数据入库（包括智能切分）
3. 验证写入结果
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / ".env")

from src.qa_full_flow.data_pipeline.loaders.tapd_loader import TapdLoader
from src.qa_full_flow.data_pipeline.pipeline import DataPipeline
from src.qa_full_flow.data_pipeline.chunker import RecursiveCharacterSplitter
from src.qa_full_flow.embedding.embedder import Embedder
from src.qa_full_flow.vector_store.chroma_store import ChromaStore


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_json(data, max_length=800):
    """格式化打印 JSON 数据"""
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    if len(json_str) > max_length:
        print(json_str[:max_length])
        print(f"\n... (内容过长，已截断，总长度: {len(json_str)} 字符)")
    else:
        print(json_str)


def main():
    """主测试流程"""
    print_section("ChromaDB 写入测试")
    
    # 检查配置
    workspace_id = os.getenv("TAPD_WORKSPACE_ID")
    api_user = os.getenv("TAPD_API_USER")
    api_password = os.getenv("TAPD_API_PASSWORD")
    
    if not all([workspace_id, api_user, api_password]):
        print("❌ 缺少 TAPD 配置，请在 .env 文件中配置以下变量:")
        print("   TAPD_WORKSPACE_ID=你的项目ID")
        print("   TAPD_API_USER=你的API用户名")
        print("   TAPD_API_PASSWORD=你的API口令")
        sys.exit(1)
    
    print(f"配置信息:")
    print(f"  Workspace ID: {workspace_id}")
    print(f"  API User: {api_user}")
    
    # 1. 初始化组件
    print_section("步骤 1: 初始化组件")
    
    try:
        print("初始化 Embedder...")
        embedder = Embedder()
        print("✅ Embedder 初始化成功")
        
        print("初始化 ChromaStore...")
        vector_store = ChromaStore()
        print(f"✅ ChromaStore 初始化成功，当前文档数: {vector_store.count()}")
        
        print("初始化 Chunker...")
        chunker = RecursiveCharacterSplitter(
            chunk_size=800,
            chunk_overlap=100
        )
        print(f"✅ Chunker 初始化成功 (chunk_size=800, overlap=100)")
        
        print("初始化 DataPipeline...")
        pipeline = DataPipeline(embedder, vector_store, chunker=chunker)
        print("✅ DataPipeline 初始化成功")
        
    except Exception as e:
        print(f"❌ 组件初始化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 2. 初始化 TapdLoader
    print_section("步骤 2: 初始化 TapdLoader")
    
    try:
        loader = TapdLoader(
            workspace_id=workspace_id,
            api_user=api_user,
            api_password=api_password
        )
        print("✅ TapdLoader 初始化成功")
        
        if loader.test_connection():
            print("✅ 连接测试成功")
        else:
            print("❌ 连接测试失败")
            sys.exit(1)
    except Exception as e:
        print(f"❌ TapdLoader 初始化失败: {e}")
        sys.exit(1)
    
    # 3. 测试 Wiki 写入（长文档，会切分）
    print_section("步骤 3: 测试 Wiki 写入（长文档，会切分）")
    
    try:
        print("正在从 TAPD 获取 Wiki 数据...")
        wikis = loader.load(
            source=workspace_id,
            resource_type="wikis",
            max_results=3  # 只获取 3 条测试
        )
        print(f"✅ 获取到 {len(wikis)} 条 Wiki")
        
        if wikis:
            # 显示第一条 Wiki 的长度
            first_wiki = wikis[0]
            content_len = len(first_wiki.get("content", ""))
            print(f"   第一条 Wiki 内容长度: {content_len} 字符")
            print(f"   文档 ID: {first_wiki.get('doc_id')}")
            
            # 调试：查看原始 API 返回的数据
            print(f"\n   调试：原始 Wiki 数据字段:")
            wiki_keys = list(first_wiki.keys())
            print(f"   顶层键: {wiki_keys}")
            if 'metadata' in first_wiki:
                print(f"   metadata 键: {list(first_wiki['metadata'].keys())}")
            
            if content_len > 800:
                print(f"   ⚠️  内容超过 800 字符，将被切分为 {content_len // 800 + 1} 个块")
            else:
                print(f"   ⚠️  内容较短 ({content_len} 字符)，将保持完整（但如果批量 API 不返回内容，需要单独获取）")
        
        # 执行入库
        print("\n正在执行 Wiki 数据入库...")
        wiki_stats = pipeline.ingest(
            loader,
            workspace_id,
            update_mode="incremental",
            resource_type="wikis",
            max_results=3
        )
        print(f"✅ Wiki 入库完成: {wiki_stats}")
        
    except Exception as e:
        print(f"❌ Wiki 写入测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 4. 测试 Bug 写入（短文档，不切分）
    print_section("步骤 4: 测试 Bug 写入（短文档，不切分）")
    
    try:
        print("正在从 TAPD 获取 Bug 数据...")
        bugs = loader.load(
            source=workspace_id,
            resource_type="bugs",
            max_results=3
        )
        print(f"✅ 获取到 {len(bugs)} 条 Bug")
        
        if bugs:
            first_bug = bugs[0]
            content_len = len(first_bug.get("content", ""))
            print(f"   第一条 Bug 内容长度: {content_len} 字符")
            print(f"   文档 ID: {first_bug.get('doc_id')}")
            print(f"   ✅ 将保持完整，不切分")
        
        # 执行入库
        print("\n正在执行 Bug 数据入库...")
        bug_stats = pipeline.ingest(
            loader,
            workspace_id,
            update_mode="incremental",
            resource_type="bugs",
            max_results=3
        )
        print(f"✅ Bug 入库完成: {bug_stats}")
        
    except Exception as e:
        print(f"❌ Bug 写入测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 5. 测试 Testcase 写入（短文档，不切分）
    print_section("步骤 5: 测试 Testcase 写入（短文档，不切分）")
    
    try:
        print("正在从 TAPD 获取 Testcase 数据...")
        testcases = loader.load(
            source=workspace_id,
            resource_type="testcases",
            max_results=100  # 获取全量（最多100条）
        )
        print(f"✅ 获取到 {len(testcases)} 条 Testcase")
        
        if testcases:
            first_tc = testcases[0]
            content_len = len(first_tc.get("content", ""))
            print(f"   第一条 Testcase 内容长度: {content_len} 字符")
            print(f"   文档 ID: {first_tc.get('doc_id')}")
            print(f"   ✅ 将保持完整，不切分")
        
        # 执行入库
        print("\n正在执行 Testcase 数据入库...")
        tc_stats = pipeline.ingest(
            loader,
            workspace_id,
            update_mode="force",  # 强制更新，确保全部写入
            resource_type="testcases",
            max_results=100
        )
        print(f"✅ Testcase 入库完成: {tc_stats}")
        
    except Exception as e:
        print(f"❌ Testcase 写入测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 6. 验证写入结果
    print_section("步骤 6: 验证 ChromaDB 写入结果")
    
    try:
        # 获取所有文档
        print("正在从 ChromaDB 获取所有文档...")
        all_docs = vector_store.get()
        
        total_count = len(all_docs.get("ids", []))
        print(f"✅ ChromaDB 中文档总数: {total_count}")
        
        if total_count > 0:
            # 按 source_type 统计
            print("\n按文档类型统计:")
            type_counts = {}
            chunk_counts = {"chunked": 0, "unchunked": 0}
            
            for doc_id, metadata in zip(all_docs["ids"], all_docs.get("metadatas", [])):
                source_type = metadata.get("source_type", "unknown")
                type_counts[source_type] = type_counts.get(source_type, 0) + 1
                
                if "chunk_id" in metadata:
                    chunk_counts["chunked"] += 1
                else:
                    chunk_counts["unchunked"] += 1
            
            for type_name, count in type_counts.items():
                print(f"   {type_name}: {count} 条")
            
            print(f"\n切分统计:")
            print(f"   切分后的块: {chunk_counts['chunked']} 个")
            print(f"   完整文档: {chunk_counts['unchunked']} 条")
            
            # 显示第一条和最后一条文档的详细信息
            print("\n第一条文档详情:")
            first_idx = 0
            first_doc = {
                "doc_id": all_docs["ids"][first_idx],
                "content_preview": all_docs["documents"][first_idx][:200],
                "metadata": all_docs["metadatas"][first_idx]
            }
            print_json(first_doc)
            
            # 如果有切分的文档，显示一个示例
            if chunk_counts["chunked"] > 0:
                print("\n切分文档示例:")
                for i, (doc_id, metadata) in enumerate(zip(all_docs["ids"], all_docs.get("metadatas", []))):
                    if "chunk_id" in metadata:
                        chunked_doc = {
                            "doc_id": doc_id,
                            "chunk_id": metadata.get("chunk_id"),
                            "chunk_index": metadata.get("chunk_index"),
                            "total_chunks": metadata.get("total_chunks"),
                            "content_preview": all_docs["documents"][i][:200],
                            "metadata": metadata
                        }
                        print_json(chunked_doc)
                        break
            
    except Exception as e:
        print(f"❌ 验证写入结果失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 7. 测试查询功能
    print_section("步骤 7: 测试查询功能")
    
    try:
        query_text = "库存"
        print(f"正在查询关键词: '{query_text}'")
        
        # 向量化查询
        query_embedding = embedder.encode([query_text], normalize=True)
        
        results = vector_store.query(
            query_embeddings=query_embedding,
            n_results=3,
            include=["documents", "metadatas", "distances"]
        )
        
        if results.get("ids") and results["ids"][0]:
            print(f"✅ 查询成功，返回 {len(results['ids'][0])} 条结果")
            
            for i, (doc_id, content, metadata, distance) in enumerate(zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            )):
                print(f"\n结果 {i+1}:")
                print(f"  文档 ID: {doc_id}")
                print(f"  相似度: {1 - distance:.4f}")
                print(f"  类型: {metadata.get('source_type')}")
                print(f"  内容预览: {content[:150]}...")
        else:
            print("⚠️  未查询到结果")
        
    except Exception as e:
        print(f"❌ 查询测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 8. 测试汇总
    print_section("测试汇总")
    print("✅ ChromaDB 写入测试完成！")
    print("\n你可以检查以下方面:")
    print("  1. Wiki 长文档是否被正确切分")
    print("  2. Bug/Testcase 短文档是否保持完整")
    print("  3. 元数据是否正确写入（source_type, chunk_id 等）")
    print("  4. 查询功能是否正常工作")


if __name__ == "__main__":
    main()
