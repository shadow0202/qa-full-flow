"""文档结构化预处理与 Token 预算控制

在将文档投喂给 LLM 之前：
1. 结构化解析：按标题/章节提取模块边界
2. Token 预算控制：为每类内容设定上限，超出时截断
3. 显式标注未提及内容：阻止 LLM 用经验补全
"""
import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TokenBudget:
    """Token 预算配置"""
    max_tokens: int
    current_tokens: int = 0
    truncated: bool = False

    def add(self, text: str) -> str:
        """
        添加文本，如果超出预算则截断

        Args:
            text: 要添加的文本

        Returns:
            实际添加的文本（可能被截断）
        """
        estimated_tokens = self._estimate_tokens(text)

        if self.current_tokens + estimated_tokens <= self.max_tokens:
            self.current_tokens += estimated_tokens
            return text
        else:
            # 计算剩余可使用的 token 数
            remaining = self.max_tokens - self.current_tokens
            if remaining <= 0:
                self.truncated = True
                return ""

            # 按比例截断
            ratio = remaining / estimated_tokens
            char_limit = int(len(text) * ratio)
            truncated_text = text[:char_limit]

            self.current_tokens += self._estimate_tokens(truncated_text)
            self.truncated = True

            logger.warning(
                f"⚠️  内容已截断: "
                f"原始 {estimated_tokens} tokens → "
                f"截断后 {self._estimate_tokens(truncated_text)} tokens "
                f"(预算上限: {self.max_tokens})"
            )

            return truncated_text

    def _estimate_tokens(self, text: str) -> int:
        """
        估算 token 数量

        中文：约 1.5-2 tokens/字
        英文：约 0.25-0.3 tokens/字（4字符/token）

        保守估算：中文字符数 × 2 + 英文字符数 / 4
        """
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars

        # 中文约 2 tokens/字，英文约 0.25 tokens/字
        return int(chinese_chars * 2 + other_chars / 4)

    def remaining(self) -> int:
        """剩余可用 token 数"""
        return max(0, self.max_tokens - self.current_tokens)


@dataclass
class DocumentSection:
    """文档章节"""
    title: str
    content: str
    level: int = 1  # 标题级别（1=一级标题）
    children: List['DocumentSection'] = field(default_factory=list)


class DocumentStructurer:
    """文档结构化工具

    将原始文档按标题/章节解析为结构化树，便于：
    1. 按模块边界提取内容
    2. 控制 token 预算
    3. 显式标注未提及内容
    """

    def __init__(
        self,
        prd_budget: int = 8000,
        tech_doc_budget: int = 4000,
        other_doc_budget: int = 2000,
        knowledge_budget: int = 1500,
    ):
        """
        Args:
            prd_budget: PRD 文档 token 预算
            tech_doc_budget: 技术文档 token 预算
            other_doc_budget: 补充文档 token 预算
            knowledge_budget: 知识库参考 token 预算
        """
        self.budgets = {
            "prd": TokenBudget(max_tokens=prd_budget),
            "tech_doc": TokenBudget(max_tokens=tech_doc_budget),
            "other_doc": TokenBudget(max_tokens=other_doc_budget),
            "knowledge": TokenBudget(max_tokens=knowledge_budget),
        }

    def structure_prd(self, prd_text: str, module_name: str = "") -> Dict:
        """
        结构化 PRD 文档

        Args:
            prd_text: PRD 原文
            module_name: 目标模块名称（用于提取相关章节）

        Returns:
            结构化结果
        """
        # 1. 解析文档结构
        sections = self._parse_sections(prd_text)

        # 2. 如果指定了模块，提取相关章节
        if module_name:
            relevant_sections = self._extract_module_sections(
                sections, module_name
            )
        else:
            relevant_sections = sections

        # 3. 应用 token 预算
        structured_content = self._apply_budget(
            relevant_sections, self.budgets["prd"]
        )

        # 4. 构建结构化结果
        result = {
            "module": module_name or "全文",
            "structure": self._sections_to_dict(relevant_sections),
            "content": structured_content,
            "budget_used": self.budgets["prd"].current_tokens,
            "budget_limit": self.budgets["prd"].max_tokens,
            "truncated": self.budgets["prd"].truncated,
        }

        return result

    def apply_budget_to_content(
        self,
        content: str,
        budget_type: str = "prd",
    ) -> Tuple[str, bool]:
        """
        对任意内容应用 token 预算

        Args:
            content: 原始内容
            budget_type: 预算类型

        Returns:
            (截断后的内容, 是否被截断)
        """
        budget = self.budgets.get(budget_type)
        if not budget:
            return content, False

        truncated_content = budget.add(content)
        return truncated_content, budget.truncated

    def _parse_sections(self, text: str) -> List[DocumentSection]:
        """
        解析文档的章节结构

        支持 Markdown 标题格式：# ## ### 等
        """
        sections = []
        lines = text.split('\n')
        current_section = None

        for line in lines:
            # 检测标题
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)

            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                # 创建新章节
                new_section = DocumentSection(
                    title=title,
                    content="",
                    level=level
                )

                # 根据级别添加到合适的父节点
                if level == 1:
                    sections.append(new_section)
                    current_section = new_section
                elif current_section:
                    # 简化处理：所有子章节都添加到当前章节
                    current_section.children.append(new_section)
            else:
                # 内容行
                if current_section:
                    current_section.content += line + '\n'

        return sections

    def _extract_module_sections(
        self,
        sections: List[DocumentSection],
        module_name: str
    ) -> List[DocumentSection]:
        """
        提取与指定模块相关的章节

        通过标题关键词匹配
        """
        relevant = []

        for section in sections:
            # 检查标题是否包含模块名
            if module_name.lower() in section.title.lower():
                relevant.append(section)
            else:
                # 检查子章节
                child_matches = [
                    child for child in section.children
                    if module_name.lower() in child.title.lower()
                ]
                if child_matches:
                    # 创建新章节只包含匹配的子章节
                    filtered_section = DocumentSection(
                        title=section.title,
                        content=section.content,
                        level=section.level,
                        children=child_matches
                    )
                    relevant.append(filtered_section)

        # 如果没有匹配，返回全文（保证不丢失信息）
        if not relevant:
            logger.warning(
                f"⚠️  未找到模块 '{module_name}' 相关章节，返回全文"
            )
            return sections

        return relevant

    def _apply_budget(
        self,
        sections: List[DocumentSection],
        budget: TokenBudget
    ) -> str:
        """
        对章节应用 token 预算
        """
        content_parts = []

        for section in sections:
            # 构建章节文本
            section_text = f"\n# {section.title}\n{section.content}"

            for child in section.children:
                section_text += f"\n## {child.title}\n{child.content}"

            # 应用预算控制
            truncated = budget.add(section_text)
            if truncated:
                content_parts.append(truncated)
            else:
                break  # 预算用尽，停止添加

        return '\n'.join(content_parts)

    def _sections_to_dict(
        self,
        sections: List[DocumentSection]
    ) -> List[Dict]:
        """将章节列表转换为字典（用于结构化输出）"""
        result = []

        for section in sections:
            section_dict = {
                "title": section.title,
                "level": section.level,
                "content_length": len(section.content),
            }

            if section.children:
                section_dict["children"] = [
                    {
                        "title": child.title,
                        "level": child.level,
                        "content_length": len(child.content),
                    }
                    for child in section.children
                ]

            result.append(section_dict)

        return result

    def generate_explicit_constraints(
        self,
        structured_prd: Dict,
        all_modules: List[str],
        target_module: str
    ) -> Dict:
        """
        生成显式约束信息

        明确告知 LLM 哪些内容在文档中未提及，阻止经验补全。

        Args:
            structured_prd: 结构化 PRD 结果
            all_modules: 所有模块列表
            target_module: 目标模块

        Returns:
            约束信息字典
        """
        # 提取 PRD 中明确提到的内容
        mentioned_features = set()
        content = structured_prd.get("content", "")

        # 简单关键词提取（可以改进为 NLP）
        common_features = [
            "密码强度", "登录频率限制", "验证码有效期",
            "会话超时", "并发登录", "第三方登录",
            "权限控制", "数据加密", "审计日志",
        ]

        for feature in common_features:
            if feature in content:
                mentioned_features.add(feature)

        # 目标模块未提及的功能
        explicitly_not_mentioned = [
            f for f in common_features
            if f not in mentioned_features
        ]

        return {
            "target_module": target_module,
            "mentioned_features": list(mentioned_features),
            "explicitly_not_mentioned": explicitly_not_mentioned,
            "warning": (
                "以下功能在 PRD 中未提及，请勿凭经验补充："
                + "、".join(explicitly_not_mentioned)
            ) if explicitly_not_mentioned else ""
        }


def preprocess_documents(
    prd_content: str,
    module_name: str,
    tech_docs: Optional[List[str]] = None,
    other_docs: Optional[List[str]] = None,
    budgets: Optional[Dict[str, int]] = None,
) -> Dict:
    """
    便捷函数：预处理所有文档

    Args:
        prd_content: PRD 文档内容
        module_name: 目标模块名称
        tech_docs: 技术文档列表
        other_docs: 补充文档列表
        budgets: 自定义 token 预算

    Returns:
        预处理结果字典
    """
    # 创建结构化工具
    if budgets:
        structurer = DocumentStructurer(
            prd_budget=budgets.get("prd", 8000),
            tech_doc_budget=budgets.get("tech_doc", 4000),
            other_doc_budget=budgets.get("other_doc", 2000),
            knowledge_budget=budgets.get("knowledge", 1500),
        )
    else:
        structurer = DocumentStructurer()

    # 1. 结构化 PRD
    prd_structured = structurer.structure_prd(prd_content, module_name)

    # 2. 处理技术文档
    tech_processed = []
    if tech_docs:
        for i, doc in enumerate(tech_docs):
            truncated, was_truncated = structurer.apply_budget_to_content(
                doc, "tech_doc"
            )
            tech_processed.append({
                "content": truncated,
                "truncated": was_truncated,
                "index": i
            })

    # 3. 处理补充文档
    other_processed = []
    if other_docs:
        for i, doc in enumerate(other_docs):
            truncated, was_truncated = structurer.apply_budget_to_content(
                doc, "other_doc"
            )
            other_processed.append({
                "content": truncated,
                "truncated": was_truncated,
                "index": i
            })

    # 4. 生成显式约束
    constraints = structurer.generate_explicit_constraints(
        prd_structured,
        all_modules=[module_name],  # 可以传入更多模块
        target_module=module_name
    )

    return {
        "prd": prd_structured,
        "tech_docs": tech_processed,
        "other_docs": other_processed,
        "constraints": constraints,
        "budgets_used": {
            k: v.current_tokens
            for k, v in structurer.budgets.items()
        },
        "any_truncated": any(v.truncated for v in structurer.budgets.values()),
    }
