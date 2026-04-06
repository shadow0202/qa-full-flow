"""定时同步任务 - 定期从JIRA/Confluence更新知识库"""
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent))

from src.config import settings
from src.embedding.embedder import Embedder
from src.vector_store.chroma_store import ChromaStore
from src.data_pipeline.pipeline import DataPipeline
from src.data_pipeline.loaders import JiraLoader, ConfluenceLoader

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("data/sync.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SyncScheduler:
    """定时同步调度器"""
    
    def __init__(self, sync_interval_hours: int = 6):
        """
        初始化同步调度器
        
        Args:
            sync_interval_hours: 同步间隔（小时）
        """
        self.sync_interval = sync_interval_hours * 3600  # 转换为秒
        self.last_sync_time = None
        self.sync_count = 0
        self.error_count = 0
        
        # 初始化服务
        logger.info("📥 正在初始化向量库...")
        self.embedder = Embedder()
        self.vector_store = ChromaStore()
        self.pipeline = DataPipeline(self.embedder, self.vector_store)
        
        # 初始化加载器
        self.jira = None
        self.confluence = None
        self._init_loaders()
        
        logger.info(f"✅ 同步调度器已初始化，间隔: {sync_interval_hours}小时")
    
    def _init_loaders(self):
        """初始化数据加载器"""
        # 初始化JIRA
        if settings.JIRA_API_TOKEN:
            try:
                self.jira = JiraLoader(
                    url=settings.JIRA_URL,
                    email=settings.JIRA_EMAIL,
                    api_token=settings.JIRA_API_TOKEN,
                    project_key=settings.JIRA_PROJECT_KEY
                )
                logger.info("✅ JIRA加载器已初始化")
            except Exception as e:
                logger.warning(f"⚠️  JIRA加载器初始化失败: {e}")
        else:
            logger.info("ℹ️  未配置JIRA API Token，跳过JIRA同步")
        
        # 初始化Confluence
        if settings.CONFLUENCE_API_TOKEN:
            try:
                self.confluence = ConfluenceLoader(
                    url=settings.CONFLUENCE_URL,
                    email=settings.CONFLUENCE_EMAIL,
                    api_token=settings.CONFLUENCE_API_TOKEN
                )
                logger.info("✅ Confluence加载器已初始化")
            except Exception as e:
                logger.warning(f"⚠️  Confluence加载器初始化失败: {e}")
        else:
            logger.info("ℹ️  未配置Confluence API Token，跳过Confluence同步")
    
    def run_sync(self):
        """执行一次同步任务（只同步 bug 和 doc）"""
        logger.info("\n" + "="*60)
        logger.info("🔄 开始定时同步任务（增量模式）...")
        logger.info("="*60)

        sync_start = datetime.now()
        total_new = 0
        total_updated = 0
        errors = []

        # 1. 同步JIRA数据（Bug）
        if self.jira:
            try:
                logger.info("\n📥 同步JIRA Bug数据...")
                # 使用增量更新模式
                stats = self.pipeline.ingest(
                    self.jira,
                    "",
                    update_mode="incremental",
                    issue_type="Bug"
                )
                total_new += stats.get("ingested", 0)
                total_updated += stats.get("updated", 0)
                logger.info(f"✅ JIRA同步完成: {stats}")
            except Exception as e:
                error_msg = f"JIRA同步失败: {e}"
                logger.error(f"❌ {error_msg}")
                errors.append(error_msg)
        else:
            logger.info("ℹ️  JIRA未配置，跳过同步")

        # 2. 同步Confluence数据（Doc）
        if self.confluence:
            try:
                logger.info("\n📥 同步Confluence文档数据...")
                # 使用增量更新模式
                stats = self.pipeline.ingest(
                    self.confluence,
                    "",
                    update_mode="incremental"
                )
                total_new += stats.get("ingested", 0)
                total_updated += stats.get("updated", 0)
                logger.info(f"✅ Confluence同步完成: {stats}")
            except Exception as e:
                error_msg = f"Confluence同步失败: {e}"
                logger.error(f"❌ {error_msg}")
                errors.append(error_msg)
        else:
            logger.info("ℹ️  Confluence未配置，跳过同步")

        # 3. 记录同步结果
        sync_end = datetime.now()
        duration = (sync_end - sync_start).total_seconds()

        self.sync_count += 1
        self.last_sync_time = sync_end

        logger.info("\n" + "="*60)
        logger.info("📊 同步结果汇总")
        logger.info("="*60)
        logger.info(f"新增/更新文档: {total_new}")
        logger.info(f"其中更新的文档: {total_updated}")
        logger.info(f"耗时: {duration:.2f}秒")
        logger.info(f"累计同步次数: {self.sync_count}")

        if errors:
            self.error_count += len(errors)
            logger.warning(f"错误数: {len(errors)}")
            for err in errors:
                logger.warning(f"  - {err}")

        logger.info(f"下次同步时间: {self._get_next_sync_time()}")
        logger.info("="*60 + "\n")
    
    def _get_next_sync_time(self) -> str:
        """获取下次同步时间"""
        if self.last_sync_time:
            next_time = self.last_sync_time + timedelta(seconds=self.sync_interval)
            return next_time.strftime("%Y-%m-%d %H:%M:%S")
        return "未知"
    
    def start(self):
        """启动定时同步任务"""
        logger.info("\n" + "="*60)
        logger.info("🚀 启动定时同步任务")
        logger.info("="*60)
        logger.info(f"同步间隔: {self.sync_interval // 3600} 小时")
        logger.info("按 Ctrl+C 停止\n")
        
        try:
            while True:
                try:
                    # 执行同步
                    self.run_sync()
                    
                    # 等待下次同步
                    logger.info(f"💤 进入休眠，将在 {self.sync_interval // 3600} 小时后唤醒...")
                    time.sleep(self.sync_interval)
                    
                except KeyboardInterrupt:
                    logger.info("\n👋 收到停止信号")
                    break
                except Exception as e:
                    logger.error(f"❌ 同步任务异常: {e}")
                    self.error_count += 1
                    # 等待一段时间后重试
                    logger.info("⏳ 10分钟后重试...")
                    time.sleep(600)  # 10分钟
        
        except KeyboardInterrupt:
            logger.info("\n👋 同步任务已停止")
        
        # 输出最终统计
        logger.info("\n" + "="*60)
        logger.info("📊 运行统计")
        logger.info("="*60)
        logger.info(f"成功同步次数: {self.sync_count}")
        logger.info(f"错误次数: {self.error_count}")
        logger.info(f"最后同步时间: {self.last_sync_time}")
        logger.info("="*60)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="定时同步JIRA/Confluence数据到知识库")
    parser.add_argument(
        "--interval", 
        type=int, 
        default=6,
        help="同步间隔（小时），默认6小时"
    )
    parser.add_argument(
        "--once", 
        action="store_true",
        help="只执行一次同步，不循环"
    )
    
    args = parser.parse_args()
    
    # 创建调度器
    scheduler = SyncScheduler(sync_interval_hours=args.interval)
    
    if args.once:
        # 只执行一次
        scheduler.run_sync()
    else:
        # 定时执行
        scheduler.start()


if __name__ == "__main__":
    main()
