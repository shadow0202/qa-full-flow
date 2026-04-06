from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置管理"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 应用配置
    APP_NAME: str = Field(default="qa-full-flow", description="应用名称")
    APP_VERSION: str = Field(default="0.1.0", description="应用版本")
    DEBUG: bool = Field(default=False, description="调试模式")

    # API配置
    API_HOST: str = Field(default="0.0.0.0", description="API服务器主机")
    API_PORT: int = Field(default=8000, description="API服务器端口")

    # Embedding配置
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-large-zh-v1.5", description="Embedding模型名称")
    EMBEDDING_DEVICE: str = Field(default="cpu", description="Embedding设备 (cpu/cuda)")

    # ChromaDB配置
    CHROMA_PATH: str = Field(default="./chroma_db", description="ChromaDB存储路径")
    CHROMA_COLLECTION_NAME: str = Field(default="test_cases", description="ChromaDB集合名称")

    # LLM配置
    LLM_API_KEY: str = Field(default="", description="LLM API密钥")
    LLM_BASE_URL: str = Field(default="", description="LLM API基础URL")
    LLM_MODEL: str = Field(default="gpt-4", description="LLM模型名称")

    # Confluence配置
    CONFLUENCE_URL: str = Field(default="", description="Confluence服务器URL")
    CONFLUENCE_EMAIL: str = Field(default="", description="Confluence邮箱")
    CONFLUENCE_API_TOKEN: str = Field(default="", description="Confluence API Token")

    # JIRA配置
    JIRA_URL: str = Field(default="", description="JIRA服务器URL")
    JIRA_EMAIL: str = Field(default="", description="JIRA邮箱")
    JIRA_API_TOKEN: str = Field(default="", description="JIRA API Token")

    @property
    def llm_available(self) -> bool:
        """检查LLM配置是否可用"""
        return bool(self.LLM_API_KEY and self.LLM_BASE_URL and self.LLM_MODEL)

    @property
    def confluence_available(self) -> bool:
        """检查Confluence配置是否可用"""
        return bool(self.CONFLUENCE_URL and self.CONFLUENCE_EMAIL and self.CONFLUENCE_API_TOKEN)


settings = Settings()
