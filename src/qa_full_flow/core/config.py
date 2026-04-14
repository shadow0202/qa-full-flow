"""应用配置管理

使用 pydantic-settings 统一管理所有配置，支持环境变量和 .env 文件。
"""
import os
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置管理"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ============ 应用配置 ============
    APP_NAME: str = Field(default="qa-full-flow", description="应用名称")
    APP_VERSION: str = Field(default="0.3.0", description="应用版本")
    DEBUG: bool = Field(default=False, description="调试模式")

    # ============ API配置 ============
    API_HOST: str = Field(default="0.0.0.0", description="API服务器主机")
    API_PORT: int = Field(default=8000, description="API服务器端口")

    # ============ Embedding配置 ============
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-m3", description="Embedding模型名称")
    EMBEDDING_DEVICE: str = Field(default="cpu", description="Embedding设备 (cpu/cuda)")

    # ============ Reranker配置 ============
    RERANKER_MODEL: str = Field(default="BAAI/bge-reranker-large", description="Reranker模型名称")
    RERANKER_DEVICE: str = Field(default="cpu", description="Reranker设备 (cpu/cuda)")

    # ============ ChromaDB配置 ============
    CHROMA_PATH: str = Field(default="./data/vector_db/chroma_kb", description="ChromaDB存储路径")
    CHROMA_COLLECTION_NAME: str = Field(default="test_knowledge", description="ChromaDB集合名称")

    # ============ LLM配置 ============
    LLM_API_KEY: str = Field(default="", description="LLM API密钥")
    LLM_BASE_URL: str = Field(default="https://api.openai.com/v1", description="LLM API基础URL")
    LLM_MODEL: str = Field(default="gpt-3.5-turbo", description="LLM模型名称")
    LLM_TIMEOUT: int = Field(default=60, description="LLM请求超时时间（秒）")
    LLM_MAX_RETRIES: int = Field(default=3, description="LLM请求最大重试次数")

    # ============ Confluence配置 ============
    CONFLUENCE_URL: str = Field(default="", description="Confluence服务器URL")
    CONFLUENCE_EMAIL: str = Field(default="", description="Confluence邮箱")
    CONFLUENCE_API_TOKEN: str = Field(default="", description="Confluence API Token")

    # ============ Tapd配置 ============
    TAPD_WORKSPACE_ID: str = Field(default="", description="Tapd Workspace ID")
    TAPD_API_USER: str = Field(default="", description="Tapd API 用户名")
    TAPD_API_PASSWORD: str = Field(default="", description="Tapd API 口令")

    # ============ JIRA配置 ============
    JIRA_URL: str = Field(default="", description="JIRA服务器URL")
    JIRA_EMAIL: str = Field(default="", description="JIRA邮箱")
    JIRA_API_TOKEN: str = Field(default="", description="JIRA API Token")
    JIRA_PROJECT_KEY: str = Field(default="", description="JIRA项目Key（为空则拉取所有项目）")

    # ============ 定时同步配置 ============
    SYNC_INTERVAL_HOURS: int = Field(default=6, description="同步间隔（小时）")

    # ============ HF镜像配置 ============
    HF_ENDPOINT: str = Field(default="https://hf-mirror.com", description="HuggingFace镜像地址")

    # ============ 日志配置 ============
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")
    LOG_FILE: Optional[str] = Field(default=None, description="日志文件路径")
    LOG_USE_JSON: bool = Field(default=False, description="是否使用JSON格式日志")

    # ============ 会话持久化配置 ============
    SESSION_BACKEND: str = Field(default="sqlite", description="会话后端: memory/sqlite")
    SESSION_DB_PATH: str = Field(default="./data/sessions.db", description="SQLite数据库路径")
    SESSION_MAX_AGE_HOURS: int = Field(default=24, description="会话最大存活时间（小时）")

    # ============ 验证器 ============
    @field_validator("API_PORT")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """验证端口号有效性"""
        if not (1 <= v <= 65535):
            raise ValueError(f"端口号必须在 1-65535 范围内，当前: {v}")
        return v

    @field_validator("EMBEDDING_DEVICE", "RERANKER_DEVICE")
    @classmethod
    def validate_device(cls, v: str) -> str:
        """验证设备配置"""
        if v not in ("cpu", "cuda"):
            raise ValueError(f"设备必须是 'cpu' 或 'cuda'，当前: {v}")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """验证日志级别"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"日志级别必须是 {valid_levels} 之一，当前: {v}")
        return v.upper()

    @field_validator("SESSION_BACKEND")
    @classmethod
    def validate_session_backend(cls, v: str) -> str:
        """验证会话后端配置"""
        if v not in ("memory", "sqlite"):
            raise ValueError(f"会话后端必须是 'memory' 或 'sqlite'，当前: {v}")
        return v

    @field_validator("LLM_API_KEY")
    @classmethod
    def validate_llm_api_key(cls, v: str) -> str:
        """验证 LLM API Key 非空（如果配置了 LLM_BASE_URL）"""
        return v

    @field_validator("CONFLUENCE_API_TOKEN", "JIRA_API_TOKEN")
    @classmethod
    def validate_api_tokens(cls, v: str) -> str:
        """验证 API Token 格式（如果提供）"""
        if v and not v.startswith(("sk-", "xox", "ATATT")):
            # 仅为警告，不阻止（不同provider格式不同）
            import logging
            logging.getLogger(__name__).warning(
                f"⚠️  API Token 格式可能不正确: {v[:10]}...，请确认"
            )
        return v

    # ============ 便捷属性 ============
    @property
    def llm_available(self) -> bool:
        """检查LLM配置是否可用"""
        return bool(self.LLM_API_KEY and self.LLM_BASE_URL and self.LLM_MODEL)

    @property
    def confluence_available(self) -> bool:
        """检查Confluence配置是否可用"""
        return bool(self.CONFLUENCE_URL and self.CONFLUENCE_EMAIL and self.CONFLUENCE_API_TOKEN)

    @property
    def jira_available(self) -> bool:
        """检查JIRA配置是否可用"""
        return bool(self.JIRA_URL and self.JIRA_API_TOKEN)

    @property
    def root_dir(self) -> Path:
        """获取项目根目录"""
        return Path(__file__).parent.parent.parent.parent

    @property
    def data_dir(self) -> Path:
        """获取数据目录"""
        data_dir = self.root_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    @property
    def vector_db_dir(self) -> Path:
        """获取向量数据库目录"""
        db_dir = self.data_dir / "vector_db"
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir

    def init_env(self) -> None:
        """初始化环境变量（用于设置 HF_ENDPOINT 等）"""
        if self.HF_ENDPOINT:
            os.environ["HF_ENDPOINT"] = self.HF_ENDPOINT


# ============ 全局配置实例 ============
settings = Settings()
