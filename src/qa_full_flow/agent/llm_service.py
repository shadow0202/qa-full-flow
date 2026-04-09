"""LLM服务 - 对接大语言模型"""
import time
import logging
from typing import Optional, Dict, Any
from openai import OpenAI
from src.qa_full_flow.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """LLM服务封装（支持 JSON mode 和重试）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = base_url or settings.LLM_BASE_URL
        self.model = model or settings.LLM_MODEL
        self.timeout = timeout or settings.LLM_TIMEOUT
        self.max_retries = max_retries or settings.LLM_MAX_RETRIES

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout
        )

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        """
        生成文本（支持指数退避重试）

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 温度参数
            max_tokens: 最大token数
            json_mode: 启用 JSON mode（强制输出 JSON）

        Returns:
            生成的文本
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                request_params: Dict[str, Any] = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }

                # 启用 JSON mode（强制输出 JSON 格式）
                if json_mode:
                    request_params["response_format"] = {"type": "json_object"}

                response = self.client.chat.completions.create(**request_params)

                return response.choices[0].message.content

            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait_time = 2.0 * (2 ** (attempt - 1))  # 指数退避：2s, 4s, 8s
                    logger.warning(
                        f"⚠️  LLM调用失败 (尝试 {attempt}/{self.max_retries}): {e}"
                    )
                    logger.info(f"⏳ {wait_time:.1f}秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"❌ LLM 调用失败，已重试 {self.max_retries} 次: {e}"
                    )

        raise Exception(f"LLM调用失败，已重试 {self.max_retries} 次: {last_error}")

    def is_available(self) -> bool:
        """检查LLM服务是否可用"""
        return bool(self.api_key)
