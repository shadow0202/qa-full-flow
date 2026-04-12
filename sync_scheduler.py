"""定时同步任务 - 定期从TAPD更新知识库"""
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent))

from src.qa_full_flow.core.config import settings
from src.qa_full_flow.core.logging import setup_logging
from src.qa_full_flow.embedding.embedder import Embedder
from src.qa_full_flow.vector_store.chroma_store import ChromaStore
from src.qa_full_flow.data_pipeline.pipeline import DataPipeline
from src.qa_full_flow.data_pipeline.chunker import RecursiveCharacterSplitter
from src.qa_full_flow.retrieval.retriever import Retriever
from src.qa_full_flow.data_pipeline.loaders.tapd_loader import TapdLoader

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

        # 初始化日志系统
        setup_logging(
            level="DEBUG" if settings.DEBUG else "INFO",
            log_file=settings.LOG_FILE or "data/sync.log",
            use_json=settings.LOG_USE_JSON,
        )

        # 初始化服务
        logger.info("初始化向量库...")
        self.embedder = Embedder()
        self.vector_store = ChromaStore()
        
        # 初始化文档切分器
        self.chunker = RecursiveCharacterSplitter(
            chunk_size=800,      # Wiki 文档切分大小
            chunk_overlap=100    # 重叠防止信息丢失
        )
        
        self.pipeline = DataPipeline(
            self.embedder, 
            self.vector_store,
            chunker=self.chunker
        )
        
        # 初始化检索器（用于 BM25 索引重建）
        self.retriever = Retriever(self.embedder, self.vector_store)

        # 初始化加载器
        self.jira = None
        self.confluence = None
        self.tapd = None
        self._init_loaders()

        logger.info(f"同步调度器已初始化，间隔: {sync_interval_hours}小时")
    
    def _init_loaders(self):
        """初始化数据加载器"""
        # 初始化Tapd
        if settings.TAPD_API_USER and settings.TAPD_API_PASSWORD and settings.TAPD_WORKSPACE_ID:
            try:
                self.tapd = TapdLoader(
                    workspace_id=settings.TAPD_WORKSPACE_ID,
                    api_user=settings.TAPD_API_USER,
                    api_password=settings.TAPD_API_PASSWORD
                )
                logger.info("Tapd加载器已初始化")
            except Exception as e:
                logger.warning(f"Tapd加载器初始化失败: {e}")
        else:
            logger.info("未配置Tapd API认证信息，跳过Tapd同步")
    
    def run_sync(self):
        """执行一次同步任务（从TAPD同步Bug、Wiki、Testcase）"""
        logger.info("开始定时同步任务（增量模式）...")

        sync_start = datetime.now()
        total_new = 0
        total_updated = 0
        errors = []

        # 1. 同步Tapd数据（Bug）
        if self.tapd:
            try:
                logger.info("同步Tapd Bug数据...")
                tapd_stats = self.pipeline.ingest(
                    self.tapd,
                    self.tapd.workspace_id,
                    update_mode="incremental",
                    resource_type="bugs",
                    max_results=10000  # 全量同步
                )
                total_new += tapd_stats.get("ingested", 0)
                total_updated += tapd_stats.get("updated", 0)
                logger.info(f"Tapd Bug同步完成: {tapd_stats}")
            except Exception as e:
                error_msg = f"Tapd Bug同步失败: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

            # 2. 同步Tapd数据（Testcase）
            try:
                logger.info("同步Tapd Testcase数据...")
                tapd_stats = self.pipeline.ingest(
                    self.tapd,
                    self.tapd.workspace_id,
                    update_mode="incremental",
                    resource_type="testcases",
                    max_results=10000  # 全量同步
                )
                total_new += tapd_stats.get("ingested", 0)
                total_updated += tapd_stats.get("updated", 0)
                logger.info(f"Tapd Testcase同步完成: {tapd_stats}")
            except Exception as e:
                error_msg = f"Tapd Testcase同步失败: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

            # 3. 同步Tapd数据（Wiki/知识库文档）
            try:
                logger.info("同步Tapd Wiki数据（知识库/PRD/技术文档）...")
                tapd_stats = self.pipeline.ingest(
                    self.tapd,
                    self.tapd.workspace_id,
                    update_mode="incremental",
                    resource_type="wikis",
                    max_results=10000  # 全量同步
                )
                total_new += tapd_stats.get("ingested", 0)
                total_updated += tapd_stats.get("updated", 0)
                logger.info(f"Tapd Wiki同步完成: {tapd_stats}")
            except Exception as e:
                error_msg = f"Tapd Wiki同步失败: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        else:
            logger.info("Tapd未配置，跳过同步")

        # 5. 重建 BM25 索引（使用统一方法）
        if total_new > 0 or total_updated > 0:
            try:
                logger.info("重建 BM25 索引...")
                doc_count = self.pipeline.rebuild_bm25_index(self.retriever)
                if doc_count > 0:
                    logger.info(f"BM25 索引已重建并保存，共 {doc_count} 个文档")
            except Exception as e:
                logger.warning(f"BM25 索引重建失败: {e}")

        # 4. 记录同步结果
        sync_end = datetime.now()
        duration = (sync_end - sync_start).total_seconds()

        self.sync_count += 1
        self.last_sync_time = sync_end

        logger.info("同步结果汇总")
        logger.info(f"新增/更新文档: {total_new}")
        logger.info(f"其中更新的文档: {total_updated}")
        logger.info(f"耗时: {duration:.2f}秒")
        logger.info(f"累计同步次数: {self.sync_count}")

        if errors:
            self.error_count += len(errors)
            logger.error(f"错误数: {len(errors)}")
            for err in errors:
                logger.error(f"  - {err}")

        logger.info(f"下次同步时间: {self._get_next_sync_time()}")

    def _get_next_sync_time(self) -> str:
        """获取下次同步时间"""
        if self.last_sync_time:
            next_time = self.last_sync_time + timedelta(seconds=self.sync_interval)
            return next_time.strftime("%Y-%m-%d %H:%M:%S")
        return "未知"
    
    def start(self):
        """启动定时同步任务"""
        logger.info("启动定时同步任务")
        logger.info(f"同步间隔: {self.sync_interval // 3600} 小时")
        logger.info("按 Ctrl+C 停止\n")

        try:
            while True:
                try:
                    # 执行同步
                    self.run_sync()

                    # 等待下次同步
                    logger.info(f"进入休眠，将在 {self.sync_interval // 3600} 小时后唤醒...")
                    time.sleep(self.sync_interval)

                except KeyboardInterrupt:
                    logger.info("收到停止信号")
                    break
                except Exception as e:
                    logger.error(f"同步任务异常: {e}")
                    self.error_count += 1
                    logger.info("10分钟后重试...")
                    time.sleep(600)  # 10分钟

        except KeyboardInterrupt:
            logger.info("同步任务已停止")

        # 输出最终统计
        logger.info("运行统计")
        logger.info(f"成功同步次数: {self.sync_count}")
        logger.info(f"错误次数: {self.error_count}")
        logger.info(f"最后同步时间: {self.last_sync_time}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="定时同步TAPD数据到知识库")
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
