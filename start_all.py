"""启动API服务和定时同步任务"""
import sys
import threading
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent))

from sync_scheduler import SyncScheduler
import uvicorn


def start_api_server():
    """启动API服务"""
    print("\n" + "="*60)
    print("🌐 正在启动API服务...")
    print("="*60)

    uvicorn.run(
        "src.qa_full_flow.api.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )


def start_sync_scheduler(interval_hours: int = 6):
    """启动定时同步任务"""
    print("\n" + "="*60)
    print("🔄 正在启动定时同步任务...")
    print("="*60)
    
    scheduler = SyncScheduler(sync_interval_hours=interval_hours)
    scheduler.start()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="启动API服务和定时同步任务")
    parser.add_argument(
        "--sync-interval", 
        type=int, 
        default=6,
        help="同步间隔（小时），默认6小时"
    )
    parser.add_argument(
        "--no-sync", 
        action="store_true",
        help="不启动定时同步"
    )
    parser.add_argument(
        "--no-api", 
        action="store_true",
        help="不启动API服务"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("🚀 AI测试用例与知识库系统 - 全功能启动")
    print("="*60)
    
    threads = []
    
    # 启动API服务
    if not args.no_api:
        api_thread = threading.Thread(
            target=start_api_server,
            name="API-Server",
            daemon=True
        )
        api_thread.start()
        threads.append(("API服务", api_thread))
        print("✅ API服务已启动: http://localhost:8000")
    
    # 启动定时同步
    if not args.no_sync:
        sync_thread = threading.Thread(
            target=start_sync_scheduler,
            args=(args.sync_interval,),
            name="Sync-Scheduler",
            daemon=True
        )
        sync_thread.start()
        threads.append(("定时同步", sync_thread))
        print(f"✅ 定时同步已启动，间隔: {args.sync_interval}小时")
    
    if not threads:
        print("⚠️  没有启动任何服务！")
        print("   使用 --help 查看帮助信息")
        return
    
    print("\n" + "="*60)
    print("✅ 所有服务已就绪")
    print("="*60)
    print("\n按 Ctrl+C 停止所有服务\n")
    
    # 保持主线程运行
    try:
        # 等待所有线程
        for name, thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print("👋 正在停止所有服务...")
        print("="*60)


if __name__ == "__main__":
    main()
