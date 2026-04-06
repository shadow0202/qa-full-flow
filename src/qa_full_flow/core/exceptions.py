"""自定义异常"""


class QAFullFlowException(Exception):
    """基础异常类"""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class DocumentFetchError(QAFullFlowException):
    """文档获取失败"""

    def __init__(self, message: str, source: str = ""):
        super().__init__(
            message=f"文档获取失败 [{source}]: {message}",
            status_code=400,
        )


class SessionNotFoundError(QAFullFlowException):
    """会话不存在"""

    def __init__(self, session_id: str):
        super().__init__(
            message=f"会话不存在: {session_id}",
            status_code=404,
        )


class InvalidStateError(QAFullFlowException):
    """非法状态转换"""

    def __init__(self, current_state: str, action: str):
        super().__init__(
            message=f"当前状态 '{current_state}' 不允许执行 '{action}'",
            status_code=400,
        )


class LLMGenerationError(QAFullFlowException):
    """LLM生成错误"""

    def __init__(self, message: str):
        super().__init__(
            message=f"LLM生成失败: {message}",
            status_code=500,
        )
