"""查看 ChromaDB 中已写入的数据"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / ".env")

from src.qa_full_flow.vector_store.chroma_store import ChromaStore


def print_section(title: str):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def main():
    print_section("查看 ChromaDB 数据")
    
    # 初始化 ChromaStore
    print("正在连接 ChromaDB...")
    store = ChromaStore()
    
    # 获取绝对路径
    import os
    abs_path = os.path.abspath(store.path)
    
    print(f"✅ 已连接到 ChromaDB")
    print(f"   集合: {store.collection_name}")
    print(f"   存储路径 (相对): {store.path}")
    print(f"   存储路径 (绝对): {abs_path}")
    print(f"   目录是否存在: {os.path.exists(abs_path)}")
    print(f"   文档总数: {store.count()}")
    
    if not os.path.exists(abs_path):
        print("\n⚠️  数据目录不存在，可能之前的测试数据未保存或路径配置有误。")
        print(f"请检查路径: {abs_path}")
        return

    # 获取所有文档
    print_section("获取所有文档")
    
    all_docs = store.get()
    
    if not all_docs.get("ids"):
        print("⚠️  ChromaDB 中没有文档")
        return
    
    total = len(all_docs["ids"])
    print(f"\n📊 文档总数: {total}")
    
    # 按类型统计
    print("\n📋 按文档类型统计:")
    type_counts = {}
    chunk_counts = {"chunked": 0, "unchunked": 0}
    
    for doc_id, metadata in zip(all_docs["ids"], all_docs.get("metadatas", [])):
        source_type = metadata.get("source_type", "unknown")
        type_counts[source_type] = type_counts.get(source_type, 0) + 1
        
        if "chunk_id" in metadata:
            chunk_counts["chunked"] += 1
        else:
            chunk_counts["unchunked"] += 1
    
    for type_name, count in sorted(type_counts.items()):
        print(f"   {type_name:15s}: {count} 条")
    
    print(f"\n📦 切分统计:")
    print(f"   切分后的块: {chunk_counts['chunked']} 个")
    print(f"   完整文档: {chunk_counts['unchunked']} 条")
    
    # 显示文档列表（前 20 条）
    print_section("文档列表（前 20 条）")
    
    print(f"\n{'序号':<5} {'文档ID':<45} {'类型':<12} {'内容长度':<8}")
    print("-" * 80)
    
    for i, (doc_id, content, metadata) in enumerate(zip(
        all_docs["ids"],
        all_docs["documents"],
        all_docs.get("metadatas", [])
    )):
        if i >= 20:
            print(f"... 还有 {total - 20} 条文档")
            break
        
        source_type = metadata.get("source_type", "unknown")
        content_len = len(content)
        print(f"{i+1:<5} {doc_id:<45} {source_type:<12} {content_len:<8}")
    
    # 查看单条文档详情
    print_section("查看单条文档详情")
    
    while True:
        try:
            print("\n请输入要查看的文档序号（1-{}），或输入 'q' 退出:".format(total))
            choice = input("> ").strip()
            
            if choice.lower() == 'q':
                break
            
            idx = int(choice) - 1
            if 0 <= idx < total:
                doc_id = all_docs["ids"][idx]
                content = all_docs["documents"][idx]
                metadata = all_docs["metadatas"][idx] if all_docs.get("metadatas") else {}
                
                print(f"\n{'='*80}")
                print(f"文档 ID: {doc_id}")
                print(f"{'='*80}")
                print(f"\n元数据:")
                for key, value in metadata.items():
                    print(f"  {key}: {value}")
                
                print(f"\n内容 (前 1000 字符):")
                print(f"{'-'*80}")
                print(content[:1000])
                if len(content) > 1000:
                    print(f"\n... (内容过长，总长度: {len(content)} 字符)")
                print(f"{'-'*80}")
            else:
                print("❌ 序号超出范围")
        except ValueError:
            print("❌ 请输入有效数字")
        except KeyboardInterrupt:
            break
    
    print("\n👋 退出查看")


if __name__ == "__main__":
    main()
