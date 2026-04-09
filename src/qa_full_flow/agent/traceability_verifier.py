"""引用锚点验证工具 - 验证 LLM 生成的引用是否真实存在"""
import re
import logging
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def verify_quote_exists(
    quote: str,
    source_documents: List[str],
    threshold: float = 0.8,
) -> Tuple[bool, float, str]:
    """
    验证引用是否在原文中存在

    Args:
        quote: LLM 生成的引用文本
        source_documents: 原文档列表
        threshold: 相似度阈值（>= 此值认为存在）

    Returns:
        (是否存在, 最高相似度, 匹配片段)
    """
    if not quote or not quote.strip():
        return False, 0.0, "引用为空"

    quote = quote.strip()
    best_score = 0.0
    best_match = ""

    for doc in source_documents:
        if not doc:
            continue

        # 方法 1: 精确匹配
        if quote in doc:
            return True, 1.0, "精确匹配"

        # 方法 2: 模糊匹配（滑动窗口）
        score, match = _fuzzy_match(quote, doc)
        if score > best_score:
            best_score = score
            best_match = match[:100]  # 截取前100字符

        # 方法 3: 关键词匹配
        if best_score < threshold:
            keyword_score = _keyword_match(quote, doc)
            if keyword_score > best_score:
                best_score = keyword_score
                best_match = f"关键词匹配（{keyword_score:.2f}）"

    exists = best_score >= threshold
    return exists, best_score, best_match


def _fuzzy_match(quote: str, doc: str, window_size: int = 50) -> Tuple[float, str]:
    """
    滑动窗口模糊匹配

    在文档中滑动窗口，找到与引用最相似的片段。
    """
    quote_len = len(quote)
    if quote_len == 0 or len(doc) == 0:
        return 0.0, ""

    best_score = 0.0
    best_fragment = ""

    # 滑动窗口大小：引用长度的 0.5 到 2 倍
    min_window = max(10, int(quote_len * 0.5))
    max_window = min(len(doc), int(quote_len * 2.0))

    for window_size in range(min_window, max_window + 1, 5):
        for i in range(0, len(doc) - window_size + 1, 10):
            fragment = doc[i:i + window_size]
            score = SequenceMatcher(None, quote, fragment).ratio()
            
            if score > best_score:
                best_score = score
                best_fragment = fragment
                
                # 如果已经很高，提前返回
                if score >= 0.95:
                    return best_score, best_fragment

    return best_score, best_fragment


def _keyword_match(quote: str, doc: str) -> float:
    """
    关键词匹配

    提取引用中的关键词，检查在文档中的覆盖率。
    """
    # 提取关键词（中文按字符，英文按单词）
    keywords = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]{2,}', quote)
    
    if not keywords:
        return 0.0

    # 统计关键词在文档中的出现
    found_count = 0
    for kw in keywords:
        if kw.lower() in doc.lower():
            found_count += 1

    # 关键词覆盖率
    coverage = found_count / len(keywords) if keywords else 0.0
    
    # 要求至少 70% 的关键词都出现
    return coverage * 0.7  # 打折扣


def verify_test_case_traceability(
    test_case: Dict,
    source_documents: Dict[str, str],
    strict_mode: bool = False,
) -> Dict:
    """
    验证测试用例的可追溯性

    检查测试用例的每个字段是否能在原文档中找到依据。

    Args:
        test_case: 测试用例字典
        source_documents: 原文档字典 {"prd": "...", "tech_doc": "...", ...}
        strict_mode: 严格模式（所有字段都必须可追溯）

    Returns:
        验证结果
    """
    verification = {
        "test_case_id": test_case.get("tc_id", test_case.get("title", "unknown")),
        "traceable": True,
        "issues": [],
        "field_verifications": {}
    }

    # 合并所有源文档
    all_docs = list(source_documents.values())

    # 验证标题
    title = test_case.get("title", "")
    if title:
        exists, score, match = verify_quote_exists(title, all_docs)
        verification["field_verifications"]["title"] = {
            "exists": exists,
            "score": score,
            "match": match
        }
        if not exists and score < 0.5:
            verification["issues"].append({
                "field": "title",
                "severity": "高" if strict_mode else "中",
                "description": f"用例标题 '{title}' 在原文中找不到依据（匹配度: {score:.2f}）"
            })
            verification["traceable"] = not strict_mode

    # 验证前置条件
    precondition = test_case.get("precondition", "")
    if precondition:
        exists, score, match = verify_quote_exists(precondition, all_docs)
        verification["field_verifications"]["precondition"] = {
            "exists": exists,
            "score": score,
            "match": match
        }
        if not exists and score < 0.4:
            verification["issues"].append({
                "field": "precondition",
                "severity": "中",
                "description": f"前置条件可能在原文中不存在（匹配度: {score:.2f}）"
            })

    # 验证预期结果
    expected = test_case.get("expected_result", test_case.get("expected", ""))
    if expected:
        exists, score, match = verify_quote_exists(expected, all_docs)
        verification["field_verifications"]["expected_result"] = {
            "exists": exists,
            "score": score,
            "match": match
        }
        if not exists and score < 0.4:
            verification["issues"].append({
                "field": "expected_result",
                "severity": "中",
                "description": f"预期结果可能在原文中不存在（匹配度: {score:.2f}）"
            })

    return verification


def generate_traceability_report(
    verifications: List[Dict],
    source_documents: Dict[str, str],
) -> str:
    """
    生成可追溯性验证报告

    Args:
        verifications: verify_test_case_traceability 的结果列表
        source_documents: 原文档字典

    Returns:
        Markdown 格式的报告文本
    """
    report = []
    report.append("## 可追溯性验证报告\n")

    total = len(verifications)
    traceable = sum(1 for v in verifications if v["traceable"])
    non_traceable = total - traceable

    report.append(f"**验证总数**: {total}")
    report.append(f"**可追溯**: {traceable} ({traceable/total:.1%})")
    report.append(f"**不可追溯**: {non_traceable} ({non_traceable/total:.1%})\n")

    if non_traceable > 0:
        report.append("### ⚠️ 不可追溯的测试用例\n")
        report.append("| 用例ID | 问题字段 | 严重程度 | 问题描述 |")
        report.append("|--------|----------|----------|----------|")

        for v in verifications:
            if not v["traceable"] or v["issues"]:
                for issue in v["issues"]:
                    report.append(
                        f"| {v['test_case_id']} | {issue['field']} | "
                        f"{issue['severity']} | {issue['description']} |"
                    )

        report.append("")

    # 详细验证结果
    report.append("### 详细验证结果\n")
    report.append("| 用例ID | 标题 | 前置条件 | 预期结果 | 状态 |")
    report.append("|--------|------|----------|----------|------|")

    for v in verifications:
        title_ver = v["field_verifications"].get("title", {})
        pre_ver = v["field_verifications"].get("precondition", {})
        exp_ver = v["field_verifications"].get("expected_result", {})

        title_status = "✅" if title_ver.get("exists", False) else "⚠️"
        pre_status = "✅" if pre_ver.get("exists", False) else "⚠️"
        exp_status = "✅" if exp_ver.get("exists", False) else "⚠️"

        status = "✅ 可追溯" if v["traceable"] else "❌ 不可追溯"

        report.append(
            f"| {v['test_case_id']} | {title_status} | {pre_status} | "
            f"{exp_status} | {status} |"
        )

    return "\n".join(report)
