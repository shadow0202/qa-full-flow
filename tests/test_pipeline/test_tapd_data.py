"""TAPD 数据获取测试脚本

测试从 TAPD 获取 Bug、Testcase、Wiki 的功能
包括批量获取和单个获取
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


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_json(data, max_length=5000):
    """格式化打印 JSON 数据"""
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    if len(json_str) > max_length:
        print(json_str[:max_length])
        print(f"\n... (内容过长，已截断，总长度: {len(json_str)} 字符)")
    else:
        print(json_str)


def test_get_bugs(loader: TapdLoader, max_results: int = 3):
    """测试获取 Bug 数据（批量）"""
    print_section("测试 1: 批量获取 Bug")
    
    try:
        bugs = loader.load(
            source=loader.workspace_id,
            resource_type="bugs",
            max_results=max_results
        )
        
        print(f"✅ 成功获取 {len(bugs)} 条 Bug")
        
        if bugs:
            print("\n第一条 Bug 的数据结构:")
            print_json(bugs[0])
        
        return True
    except Exception as e:
        print(f"❌ 获取 Bug 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_testcases(loader: TapdLoader, max_results: int = 3):
    """测试获取 Testcase 数据（批量）"""
    print_section("测试 2: 批量获取 Testcase")
    
    try:
        # 先获取原始数据看看是什么格式
        import requests
        url = f"{loader.BASE_URL}/tcases"
        params = {
            "workspace_id": loader.workspace_id,
            "limit": 3,
            "page": 1
        }
        response = loader.session.get(url, params=params)
        response.raise_for_status()
        raw_data = response.json()
        
        print(f"原始 API 响应 status: {raw_data.get('status')}")
        print(f"data 数组长度: {len(raw_data.get('data', []))}")
        
        if raw_data.get('data'):
            first_item = raw_data['data'][0]
            print(f"第一条数据类型: {type(first_item)}")
            if isinstance(first_item, dict):
                print(f"第一条数据键: {list(first_item.keys())}")
                print("\n第一条 Testcase 的原始数据结构:")
                print_json(first_item)
            elif isinstance(first_item, str):
                print(f"第一条数据内容（字符串）: {first_item[:200]}")
        
        # 现在尝试使用 loader.load()
        testcases = loader.load(
            source=loader.workspace_id,
            resource_type="testcases",
            max_results=max_results
        )
        
        print(f"\n✅ 成功获取 {len(testcases)} 条 Testcase")
        
        if testcases:
            print("\n第一条 Testcase 的数据结构:")
            print_json(testcases[0])
        
        return True
    except Exception as e:
        print(f"❌ 获取 Testcase 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_wikis_batch(loader: TapdLoader, max_results: int = 3):
    """测试获取 Wiki 数据（批量）"""
    print_section("测试 3: 批量获取 Wiki")
    
    try:
        wikis = loader.load(
            source=loader.workspace_id,
            resource_type="wikis",
            max_results=max_results
        )
        
        print(f"✅ 成功获取 {len(wikis)} 条 Wiki")
        
        if wikis:
            print("\n第一条 Wiki 的数据结构:")
            print_json(wikis[0])
        
        return wikis
    except Exception as e:
        print(f"❌ 批量获取 Wiki 失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def test_get_wiki_single(loader: TapdLoader, wiki_id: str):
    """测试获取单个 Wiki"""
    print_section(f"测试 4: 获取单个 Wiki (ID: {wiki_id})")
    
    try:
        wiki = loader.get_wiki_by_id(wiki_id)
        
        if wiki:
            print(f"✅ 成功获取 Wiki: {wiki.get('doc_id')}")
            print("\nWiki 的数据结构:")
            print_json(wiki)
            return True
        else:
            print(f"⚠️  未找到 Wiki: {wiki_id}")
            return False
    except Exception as e:
        print(f"❌ 获取单个 Wiki 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试流程"""
    print_section("TAPD 数据获取测试")
    
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
    print(f"  API Password: {'*' * len(api_password)}")
    
    # 初始化 Loader
    print("\n正在初始化 TapdLoader...")
    try:
        loader = TapdLoader(
            workspace_id=workspace_id,
            api_user=api_user,
            api_password=api_password
        )
        print("✅ TapdLoader 初始化成功")
    except Exception as e:
        print(f"❌ TapdLoader 初始化失败: {e}")
        sys.exit(1)
    
    # 测试连接
    print("\n正在测试连接...")
    if loader.test_connection():
        print("✅ 连接测试成功")
    else:
        print("❌ 连接测试失败")
        sys.exit(1)
    
    # 执行测试
    results = {
        "Bug": test_get_bugs(loader, max_results=100),
        "Testcase": test_get_testcases(loader, max_results=100),
        "Wiki (批量)": False,
        "Wiki (单个)": False,
    }

    # 批量获取 Wiki
    wikis = test_get_wikis_batch(loader, max_results=100)
    if wikis:
        results["Wiki (批量)"] = True
        
        # 获取第一个 Wiki ID 进行单个获取测试
        first_wiki_id = wikis[0].get("metadata", {}).get("tapd_id")
        if first_wiki_id:
            results["Wiki (单个)"] = test_get_wiki_single(loader, first_wiki_id)
    
    # 打印测试结果汇总
    print_section("测试结果汇总")
    
    for test_name, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {test_name:20s} {status}")
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    print(f"\n总计: {success_count}/{total_count} 项测试通过")
    
    if success_count == total_count:
        print("\n🎉 所有测试通过！TAPD 数据获取功能正常。")
    else:
        print("\n⚠️  部分测试失败，请检查上面的错误信息。")


if __name__ == "__main__":
    main()
