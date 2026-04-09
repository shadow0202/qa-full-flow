"""语义匹配工具 - 用于覆盖率分析和相似性计算"""
import logging
from typing import List, Dict, Tuple, Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def calculate_similarity(text1: str, text2: str, method: str = "hybrid") -> float:
    """
    计算两个文本的相似度

    Args:
        text1: 文本1
        text2: 文本2
        method: 计算方法
            - "sequence": 序列匹配（适合短文本）
            - "token": Token 重叠（适合中等文本）
            - "hybrid": 混合方法（推荐）

    Returns:
        相似度分数 (0.0 - 1.0)
    """
    if not text1 or not text2:
        return 0.0

    text1 = text1.lower().strip()
    text2 = text2.lower().strip()

    if method == "sequence":
        return _sequence_similarity(text1, text2)
    elif method == "token":
        return _token_overlap(text1, text2)
    else:  # hybrid
        seq_score = _sequence_similarity(text1, text2)
        token_score = _token_overlap(text1, text2)
        # 混合评分：序列匹配 60% + Token 重叠 40%
        return 0.6 * seq_score + 0.4 * token_score


def _sequence_similarity(text1: str, text2: str) -> float:
    """序列匹配相似度"""
    return SequenceMatcher(None, text1, text2).ratio()


def _token_overlap(text1: str, text2: str) -> float:
    """Token 重叠相似度"""
    # 简单分词（中文按字符，英文按空格）
    tokens1 = set(_tokenize(text1))
    tokens2 = set(_tokenize(text2))

    if not tokens1 or not tokens2:
        return 0.0

    # Jaccard 相似度
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    
    return len(intersection) / len(union) if union else 0.0


def _tokenize(text: str) -> List[str]:
    """简单分词"""
    # 移除标点符号，按字符/单词分割
    import re
    # 保留中文、英文、数字
    tokens = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', text)
    return tokens


def match_function_points(
    test_cases: List[Dict],
    function_points: List[str],
    threshold: float = 0.3,
    use_title: bool = True,
    use_steps: bool = True,
) -> Dict[str, Dict]:
    """
    匹配测试用例和功能点

    Args:
        test_cases: 测试用例列表
        function_points: 功能点列表
        threshold: 相似度阈值（>= 此值认为已覆盖）
        use_title: 是否使用用例标题匹配
        use_steps: 是否使用测试步骤匹配

    Returns:
        匹配结果字典 {功能点: {covered: bool, matched_tc: [...], score: float}}
    """
    results = {}

    for fp in function_points:
        if not fp or not fp.strip():
            continue

        best_match = {
            "covered": False,
            "matched_tc": [],
            "score": 0.0,
            "match_method": "none"
        }

        for tc in test_cases:
            # 计算匹配分数
            score = 0.0
            match_details = []

            # 1. 标题匹配
            if use_title:
                title = tc.get("title", "")
                title_score = calculate_similarity(fp, title, method="hybrid")
                if title_score > score:
                    score = title_score
                    match_details.append(f"title({title_score:.2f})")

            # 2. 测试步骤匹配
            if use_steps:
                steps = tc.get("test_steps", tc.get("steps", ""))
                if isinstance(steps, list):
                    steps_text = " ".join(steps)
                else:
                    steps_text = str(steps)
                
                steps_score = calculate_similarity(fp, steps_text, method="hybrid")
                if steps_score > score:
                    score = steps_score
                    match_details.append(f"steps({steps_score:.2f})")

            # 如果超过阈值，认为已覆盖
            if score >= threshold:
                best_match["covered"] = True
                best_match["matched_tc"].append(tc.get("tc_id", tc.get("title", "unknown")))
                best_match["score"] = max(best_match["score"], score)
                best_match["match_method"] = ", ".join(match_details)

        results[fp] = best_match

    return results


def calculate_coverage_rate(
    match_results: Dict[str, Dict],
    weighted: bool = True,
) -> float:
    """
    计算覆盖率

    Args:
        match_results: match_function_points 的返回结果
        weighted: 是否使用加权计算（根据匹配分数）

    Returns:
        覆盖率 (0.0 - 1.0)
    """
    if not match_results:
        return 0.0

    total = len(match_results)
    
    if weighted:
        # 加权覆盖率：考虑匹配分数
        total_score = sum(
            result["score"] if result["covered"] else 0.0
            for result in match_results.values()
        )
        return total_score / total if total > 0 else 0.0
    else:
        # 简单覆盖率：只要超过阈值就算覆盖
        covered = sum(1 for result in match_results.values() if result["covered"])
        return covered / total if total > 0 else 0.0


def get_coverage_details(match_results: Dict[str, Dict]) -> Dict[str, List]:
    """
    获取覆盖详情

    Args:
        match_results: match_function_points 的返回结果

    Returns:
        {"covered": [...], "uncovered": [...], "partial": [...]}
    """
    covered = []
    uncovered = []
    partial = []

    for fp, result in match_results.items():
        detail = {
            "function_point": fp,
            "covered": result["covered"],
            "score": result["score"],
            "matched_test_cases": result["matched_tc"],
            "match_method": result["match_method"]
        }

        if result["covered"]:
            if result["score"] >= 0.6:
                covered.append(detail)
            else:
                partial.append(detail)
        else:
            uncovered.append(detail)

    return {
        "covered": covered,
        "partial": partial,
        "uncovered": uncovered
    }


def generate_coverage_summary(match_results: Dict[str, Dict]) -> str:
    """
    生成覆盖率摘要（用于报告）

    Args:
        match_results: match_function_points 的返回结果

    Returns:
        格式化的摘要文本
    """
    if not match_results:
        return "无功能点可供分析"

    total = len(match_results)
    covered = sum(1 for r in match_results.values() if r["covered"])
    uncovered = total - covered
    avg_score = sum(r["score"] for r in match_results.values()) / total if total > 0 else 0.0

    summary = []
    summary.append(f"**功能点总数**: {total}")
    summary.append(f"**已覆盖**: {covered} ({covered/total:.1%})")
    summary.append(f"**未覆盖**: {uncovered} ({uncovered/total:.1%})")
    summary.append(f"**平均匹配度**: {avg_score:.2f}")
    
    return "\n".join(summary)
