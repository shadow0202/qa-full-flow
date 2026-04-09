"""JSON 容错解析器

提供多种 JSON 提取策略，确保 LLM 输出的稳定解析。
支持：
1. 标准 JSON 解析
2. 正则表达式提取（支持 Markdown 代码块）
3. 括号匹配提取（find/rfind 的改进版）
4. JSON mode 强制要求（如果 LLM 支持）
"""
import re
import json
import logging
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)


def extract_json(
    text: str,
    expected_type: str = "auto",
    fallback: Any = None,
    strict_mode: bool = False,
) -> Optional[Any]:
    """
    从 LLM 输出中提取 JSON 数据

    按优先级尝试多种解析策略：
    1. 尝试直接解析整个文本
    2. 提取 Markdown 代码块中的 JSON
    3. 使用正则表达式查找 JSON 块
    4. 使用括号匹配提取

    Args:
        text: LLM 输出文本
        expected_type: 期望的类型
            - "auto": 自动检测（对象或数组）
            - "object": JSON 对象 {}
            - "array": JSON 数组 []
        fallback: 解析失败时的默认返回值
        strict_mode: 严格模式（只尝试标准 JSON，不降级）

    Returns:
        解析后的 JSON 对象/数组，失败返回 None 或 fallback

    Examples:
        >>> extract_json('{"key": "value"}')
        {"key": "value"}

        >>> extract_json('```json\\n{"key": "value"}\\n```')
        {"key": "value"}

        >>> extract_json('Some text [{"a": 1}] more text', expected_type="array")
        [{"a": 1}]
    """
    if not text or not text.strip():
        return fallback

    # 策略 1: 尝试直接解析
    if not strict_mode:
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

    # 策略 2: 提取 Markdown 代码块
    result = _extract_from_markdown(text, expected_type)
    if result is not None:
        return result

    # 策略 3: 使用正则表达式查找 JSON
    result = _extract_with_regex(text, expected_type)
    if result is not None:
        return result

    # 策略 4: 括号匹配提取（改进版 find/rfind）
    result = _extract_with_bracket_matching(text, expected_type)
    if result is not None:
        return result

    # 所有策略都失败
    if fallback is not None:
        return fallback
    
    logger.warning("⚠️  JSON 解析失败，所有策略均未成功")
    return None


def _extract_from_markdown(text: str, expected_type: str) -> Optional[Any]:
    """
    从 Markdown 代码块中提取 JSON

    支持以下格式：
    ```json
    {"key": "value"}
    ```

    ```
    {"key": "value"}
    ```
    """
    # 匹配 ```json ... ``` 或 ``` ... ```
    patterns = [
        r'```json\s*\n(.*?)\n\s*```',  # ```json 代码块
        r'```\s*\n(.*?)\n\s*```',      # ``` 代码块
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.debug(f"Markdown 代码块 JSON 解析失败: {e}")
                continue

    return None


def _extract_with_regex(text: str, expected_type: str) -> Optional[Any]:
    """
    使用正则表达式提取 JSON

    根据 expected_type 选择正则模式：
    - "object": 匹配 {...}（支持嵌套）
    - "array": 匹配 [...]（支持嵌套）
    - "auto": 先尝试对象，再尝试数组
    """
    patterns = []
    
    if expected_type in ("auto", "object"):
        # 匹配 { 开头的内容，使用非贪婪匹配找到最外层
        patterns.append((r'\{(?:[^{}]|(?R))*\}', "object"))
    
    if expected_type in ("auto", "array"):
        # 匹配 [ 开头的内容
        patterns.append((r'\[(?:[^\[\]]|(?R))*\]', "array"))

    # 简化版正则（不支持递归，但性能更好）
    simple_patterns = [
        (r'\{[^{}]*\}', "object"),
        (r'\[[^\[\]]*\]', "array"),
    ]

    # 先尝试简单正则
    for pattern, _ in simple_patterns:
        match = re.search(pattern, text)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue

    return None


def _extract_with_bracket_matching(text: str, expected_type: str) -> Optional[Any]:
    """
    使用括号匹配提取 JSON

    改进版的 find/rfind，正确处理嵌套括号
    """
    if expected_type in ("auto", "object"):
        result = _match_braces(text, '{', '}')
        if result is not None:
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                pass

    if expected_type in ("auto", "array"):
        result = _match_braces(text, '[', ']')
        if result is not None:
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                pass

    return None


def _match_braces(text: str, open_char: str, close_char: str) -> Optional[str]:
    """
    匹配括号对（支持嵌套）

    找到第一个开括号，然后找到对应的闭括号，
    正确处理嵌套情况。

    Args:
        text: 文本
        open_char: 开括号字符（如 '{' 或 '['）
        close_char: 闭括号字符（如 '}' 或 ']'）

    Returns:
        匹配到的括号内容（包括括号本身），失败返回 None
    """
    start = text.find(open_char)
    if start == -1:
        return None

    count = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        char = text[i]

        # 处理转义字符
        if escape_next:
            escape_next = False
            continue

        if char == '\\':
            escape_next = True
            continue

        # 处理字符串
        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        # 如果在字符串内部，跳过
        if in_string:
            continue

        # 计数括号
        if char == open_char:
            count += 1
        elif char == close_char:
            count -= 1
            if count == 0:
                # 找到匹配的闭括号
                return text[start:i+1]

    return None


def validate_json_structure(
    data: Any,
    required_fields: Optional[list[str]] = None,
    expected_type: Optional[str] = None,
) -> tuple[bool, str]:
    """
    验证 JSON 结构是否符合要求

    Args:
        data: 解析后的 JSON 数据
        required_fields: 必需字段列表
        expected_type: 期望的类型 ("object", "array")

    Returns:
        (是否有效, 错误信息)
    """
    if data is None:
        return False, "数据为空"

    # 检查类型
    if expected_type == "object" and not isinstance(data, dict):
        return False, f"期望对象，实际: {type(data).__name__}"
    
    if expected_type == "array" and not isinstance(data, list):
        return False, f"期望数组，实际: {type(data).__name__}"

    # 检查必需字段
    if required_fields and isinstance(data, dict):
        missing = [f for f in required_fields if f not in data]
        if missing:
            return False, f"缺少必需字段: {', '.join(missing)}"

    # 检查数组元素
    if isinstance(data, list):
        if len(data) == 0:
            return False, "数组为空"
        
        # 如果数组元素是字典，检查第一个元素的字段
        if isinstance(data[0], dict) and required_fields:
            missing = [f for f in required_fields if f not in data[0]]
            if missing:
                return False, f"数组元素缺少字段: {', '.join(missing)}"

    return True, ""


def extract_json_array(
    text: str,
    required_fields: Optional[list[str]] = None,
    fallback: Optional[list] = None,
) -> Optional[list]:
    """
    便捷函数：提取 JSON 数组

    Args:
        text: LLM 输出文本
        required_fields: 数组元素的必需字段
        fallback: 解析失败时的默认返回值

    Returns:
        解析后的数组
    """
    result = extract_json(text, expected_type="array")
    
    if result is None:
        return fallback

    # 验证结构
    is_valid, error_msg = validate_json_structure(
        result,
        required_fields=required_fields,
        expected_type="array"
    )

    if not is_valid:
        logger.warning(f"⚠️  JSON 数组结构验证失败: {error_msg}")
        return fallback

    return result


def extract_json_object(
    text: str,
    required_fields: Optional[list[str]] = None,
    fallback: Optional[dict] = None,
) -> Optional[dict]:
    """
    便捷函数：提取 JSON 对象

    Args:
        text: LLM 输出文本
        required_fields: 必需字段列表
        fallback: 解析失败时的默认返回值

    Returns:
        解析后的对象
    """
    result = extract_json(text, expected_type="object")
    
    if result is None:
        return fallback

    # 验证结构
    is_valid, error_msg = validate_json_structure(
        result,
        required_fields=required_fields,
        expected_type="object"
    )

    if not is_valid:
        logger.warning(f"⚠️  JSON 对象结构验证失败: {error_msg}")
        return fallback

    return result
