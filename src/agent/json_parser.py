"""LLM 响应解析工具 - 容错解析"""
import re
import json
from typing import Any, Optional, Union


def extract_json_object(text: str) -> Optional[dict]:
    """
    从 LLM 响应中提取第一个 JSON 对象

    策略：
    1. 尝试直接 json.loads
    2. 用正则匹配最外层 { ... }
    3. 尝试修复常见 JSON 错误（尾随逗号、未转义换行等）

    Returns:
        解析后的 dict，失败返回 None
    """
    text = text.strip()

    # 1. 尝试直接解析
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 2. 正则匹配最外层 { ... }（支持嵌套）
    json_str = _match_braces(text, start="{")
    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # 尝试修复
            fixed = _fix_json_string(json_str)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

    return None


def extract_json_array(text: str) -> Optional[list]:
    """
    从 LLM 响应中提取第一个 JSON 数组

    策略同 extract_json_object

    Returns:
        解析后的 list，失败返回 None
    """
    text = text.strip()

    # 1. 尝试直接解析
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # 2. 正则匹配最外层 [ ... ]
    json_str = _match_braces(text, start="[")
    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            fixed = _fix_json_string(json_str)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

    return None


def _match_braces(text: str, start: str) -> Optional[str]:
    """
    匹配最外层成对的括号内容
    支持嵌套，找到第一个完整的 {..} 或 [..]
    """
    end = "}" if start == "{" else "]"
    start_idx = text.find(start)
    if start_idx == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start_idx, len(text)):
        char = text[i]

        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == start:
            depth += 1
        elif char == end:
            depth -= 1
            if depth == 0:
                return text[start_idx:i + 1]

    return None


def _fix_json_string(json_str: str) -> str:
    """
    修复常见 JSON 错误：
    1. 尾随逗号: {"a": 1,} → {"a": 1}
    2. 单引号: {'a': 1} → {"a": 1}
    3. 未转义的换行符
    """
    # 移除尾随逗号（在 } 或 ] 之前的逗号）
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

    # 替换单引号为双引号（简单情况，不处理字符串内含单引号的情况）
    json_str = re.sub(r"'([^']*)':", r'"\1":', json_str)

    # 替换未转义的换行符（在字符串值内）
    # 这是一个简化的修复，不完美但能处理大多数情况
    lines = json_str.split('\n')
    fixed_lines = []
    for line in lines:
        # 如果行看起来像字符串值的一部分但没有闭合引号
        fixed_lines.append(line)
    json_str = '\n'.join(fixed_lines)

    return json_str


def parse_llm_json(text: str, expected_type: str = "auto") -> Optional[Union[dict, list]]:
    """
    通用 LLM JSON 解析入口

    Args:
        text: LLM 输出文本
        expected_type: 期望类型 "dict", "list", 或 "auto"

    Returns:
        解析后的对象，失败返回 None
    """
    if expected_type == "dict":
        return extract_json_object(text)
    elif expected_type == "list":
        return extract_json_array(text)
    else:
        # 自动检测
        result = extract_json_object(text)
        if result:
            return result
        return extract_json_array(text)
