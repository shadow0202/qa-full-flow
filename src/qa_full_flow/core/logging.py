"""日志配置

提供灵活的日志系统，支持控制台和文件输出，以及JSON格式化选项。
"""
import logging
import sys
import json
from typing import Optional
from pathlib import Path
from logging.handlers import RotatingFileHandler


class JSONFormatter(logging.Formatter):
    """JSON格式日志，便于结构化日志分析"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if record.exc_info and record.exc_info[0]:
            log_data["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, "extra"):
            log_data["extra"] = record.extra
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None,
    use_json: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> None:
    """
    配置日志系统

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径，如果为None则只输出到控制台
        format_string: 自定义格式
        use_json: 是否使用JSON格式
        max_bytes: 日志文件最大大小（字节）
        backup_count: 保留的日志文件数量
    """
    if format_string is None:
        format_string = (
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # 选择格式化器
    formatter: logging.Formatter
    if use_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(format_string)

    # 配置根logger
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        # 确保日志目录存在
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用轮转文件处理器
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # 配置根logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    for handler in handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    # 抑制第三方库的冗余日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
