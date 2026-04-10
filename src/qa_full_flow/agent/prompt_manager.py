F"""Prompt 模板管理系统

支持从文件/数据库加载 Prompt 模板，实现在线调整而无需修改代码。
支持版本管理、环境变量注入、多语言等特性。
"""
import os
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    """单个 Prompt 模板"""
    name: str
    version: str
    content: str
    variables: List[str] = field(default_factory=list)
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def render(self, **kwargs) -> str:
        """
        渲染模板（替换变量）

        Args:
            **kwargs: 变量值

        Returns:
            渲染后的文本
        """
        try:
            return self.content.format(**kwargs)
        except KeyError as e:
            logger.error(f"❌ Prompt 模板变量缺失: {e}")
            raise ValueError(f"Prompt 模板 '{self.name}' 缺少变量: {e}")


class PromptManager:
    """Prompt 模板管理器

    支持多种加载方式：
    1. 从 Python 常量加载（向后兼容）
    2. 从 YAML/JSON 文件加载
    3. 从环境变量覆盖
    4. 热重载（监听文件变化）
    """

    def __init__(
        self,
        prompt_dir: Optional[str] = None,
        enable_hot_reload: bool = False,
        fallback_to_hardcoded: bool = True,
    ):
        """
        Args:
            prompt_dir: Prompt 模板目录路径
            enable_hot_reload: 是否启用热重载
            fallback_to_hardcoded: 文件加载失败时是否降级为硬编码
        """
        self.prompt_dir = prompt_dir or self._default_prompt_dir()
        self.enable_hot_reload = enable_hot_reload
        self.fallback_to_hardcoded = fallback_to_hardcoded

        # 缓存已加载的 Prompt
        self._templates: Dict[str, PromptTemplate] = {}
        self._file_hashes: Dict[str, str] = {}

        # 加载内置硬编码 Prompt（向后兼容）
        if fallback_to_hardcoded:
            self._load_hardcoded_prompts()

        # 从文件加载（如果存在）
        if os.path.exists(self.prompt_dir):
            self._load_from_directory()

        logger.info(f"✅ PromptManager 已初始化，共 {len(self._templates)} 个模板")

    def get(self, name: str, version: Optional[str] = None) -> PromptTemplate:
        """
        获取 Prompt 模板

        Args:
            name: Prompt 名称
            version: 版本号（可选，默认使用最新版）

        Returns:
            PromptTemplate 实例
        """
        key = name if version is None else f"{name}:{version}"

        if key not in self._templates:
            # 尝试找最新版
            if version is None:
                latest = self._get_latest_version(name)
                if latest:
                    return latest

            raise KeyError(f"Prompt 模板不存在: {key}")

        # 热重载检查
        if self.enable_hot_reload:
            self._check_for_updates()

        return self._templates[key]

    def render(self, name: str, version: Optional[str] = None, **kwargs) -> str:
        """
        获取并渲染 Prompt 模板

        Args:
            name: Prompt 名称
            version: 版本号（可选）
            **kwargs: 模板变量

        Returns:
            渲染后的文本
        """
        template = self.get(name, version)
        return template.render(**kwargs)

    def list_prompts(self) -> List[Dict[str, str]]:
        """列出所有已加载的 Prompt"""
        return [
            {
                "name": t.name,
                "version": t.version,
                "description": t.description,
                "variables": t.variables,
            }
            for t in self._templates.values()
        ]

    def reload(self) -> None:
        """重新加载所有 Prompt 模板"""
        self._templates.clear()
        self._file_hashes.clear()

        if self.fallback_to_hardcoded:
            self._load_hardcoded_prompts()

        if os.path.exists(self.prompt_dir):
            self._load_from_directory()

        logger.info(f"🔄 Prompt 模板已重新加载，共 {len(self._templates)} 个")

    # ============ 私有方法 ============

    def _default_prompt_dir(self) -> str:
        """获取默认 Prompt 模板目录"""
        return str(Path(__file__).parent / "prompts" / "templates")

    def _load_hardcoded_prompts(self) -> None:
        """加载内置硬编码 Prompt（向后兼容）"""
        from src.qa_full_flow.agent.prompts import test_analysis, test_design

        # Phase1 分析 Prompt
        self._register_template(
            name="phase1_system_prompt",
            version="v1",
            content=test_analysis.PHASE1_SYSTEM_PROMPT,
            description="阶段1：需求分析与测试点提取 - 系统提示词",
            variables=["module", "prd_content", "tech_doc_content", "other_doc_content", "knowledge_refs"],
        )

        self._register_template(
            name="phase1_user_prompt",
            version="v1",
            content=test_analysis.PHASE1_USER_PROMPT,
            description="阶段1：需求分析与测试点提取 - 用户提示词",
            variables=["module", "prd_url", "prd_content", "tech_doc_urls", "tech_doc_content", "other_doc_urls", "other_doc_content", "knowledge_refs"],
        )

        # Phase2 测试用例生成 Prompt (V3)
        self._register_template(
            name="phase2_system_prompt",
            version="v3",
            content=test_design.TEST_CASE_GENERATION_SYSTEM_PROMPT_V3,
            description="阶段2：测试用例设计生成 - 系统提示词 (V3)",
            variables=["module", "function_points"],
        )

        self._register_template(
            name="phase2_user_prompt",
            version="v3",
            content=test_design.TEST_CASE_GENERATION_USER_PROMPT_V3,
            description="阶段2：测试用例设计生成 - 用户提示词 (V3)",
            variables=["module", "function_points", "analysis_doc", "n_examples"],
        )

    def _register_template(
        self,
        name: str,
        version: str,
        content: str,
        description: str = "",
        variables: List[str] = None,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """注册一个 Prompt 模板"""
        now = datetime.now().isoformat()

        template = PromptTemplate(
            name=name,
            version=version,
            content=content,
            variables=variables or self._extract_variables(content),
            description=description,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        key = f"{name}:{version}"
        self._templates[key] = template

    def _extract_variables(self, content: str) -> List[str]:
        """从模板内容中提取变量（支持 {var} 格式）"""
        import re
        # 匹配 {variable} 格式，排除 {{escaped}}
        matches = re.findall(r'(?<!\{)\{(\w+)\}(?!\})', content)
        return list(set(matches))  # 去重

    def _get_latest_version(self, name: str) -> Optional[PromptTemplate]:
        """获取指定名称的最新版 Prompt"""
        matching = [
            t for key, t in self._templates.items()
            if t.name == name
        ]

        if not matching:
            return None

        # 按版本号排序（简单字符串比较）
        matching.sort(key=lambda t: t.version, reverse=True)
        return matching[0]

    def _load_from_directory(self) -> None:
        """从目录加载所有 Prompt 模板文件"""
        prompt_dir = Path(self.prompt_dir)

        if not prompt_dir.exists():
            return

        # 支持 YAML 和 JSON 格式
        for ext in ["*.yaml", "*.yml", "*.json"]:
            for file_path in prompt_dir.rglob(ext):
                try:
                    self._load_from_file(file_path)
                except Exception as e:
                    logger.warning(f"⚠️  加载 Prompt 文件失败 {file_path}: {e}")

    def _load_from_file(self, file_path: Path) -> None:
        """从单个文件加载 Prompt 模板"""
        with open(file_path, 'r', encoding='utf-8') as f:
            if file_path.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        # 支持单个模板或模板列表
        if isinstance(data, list):
            for item in data:
                self._register_from_dict(item)
        else:
            self._register_from_dict(data)

        # 记录文件哈希（用于热重载）
        self._file_hashes[str(file_path)] = self._file_hash(file_path)

    def _register_from_dict(self, data: Dict) -> None:
        """从字典注册 Prompt 模板"""
        required_fields = ["name", "version", "content"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Prompt 模板缺少必需字段: {field}")

        self._register_template(
            name=data["name"],
            version=data["version"],
            content=data["content"],
            description=data.get("description", ""),
            variables=data.get("variables"),
            metadata=data.get("metadata", {}),
        )

    def _file_hash(self, file_path: Path) -> str:
        """计算文件哈希（用于检测变化）"""
        import hashlib
        content = file_path.read_bytes()
        return hashlib.md5(content).hexdigest()

    def _check_for_updates(self) -> None:
        """检查文件是否有更新（热重载）"""
        prompt_dir = Path(self.prompt_dir)

        for file_path in prompt_dir.rglob("*"):
            if file_path.suffix not in ['.yaml', '.yml', '.json']:
                continue

            current_hash = self._file_hash(file_path)
            old_hash = self._file_hashes.get(str(file_path))

            if old_hash != current_hash:
                logger.info(f"🔄 检测到 Prompt 文件变化，重新加载: {file_path}")
                self._load_from_file(file_path)


# ============ 全局实例 ============
_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager(
    prompt_dir: Optional[str] = None,
    enable_hot_reload: bool = False,
) -> PromptManager:
    """
    获取全局 PromptManager 实例

    Args:
        prompt_dir: Prompt 模板目录
        enable_hot_reload: 是否启用热重载

    Returns:
        PromptManager 实例
    """
    global _prompt_manager

    if _prompt_manager is None:
        _prompt_manager = PromptManager(
            prompt_dir=prompt_dir,
            enable_hot_reload=enable_hot_reload,
        )

    return _prompt_manager


def render_prompt(name: str, version: Optional[str] = None, **kwargs) -> str:
    """
    便捷函数：获取并渲染 Prompt 模板

    Args:
        name: Prompt 名称
        version: 版本号（可选）
        **kwargs: 模板变量

    Returns:
        渲染后的文本
    """
    manager = get_prompt_manager()
    return manager.render(name, version, **kwargs)
