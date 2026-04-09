"""LLM服务 - 对接大语言模型"""
import time
import logging
from typing import Optional
from openai import OpenAI
from src.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """LLM服务封装"""

    def __init__(self, api_key: str = None, base_url: str = None,
                 model: str = None, timeout: int = 60,
                 max_retries: int = 3, retry_delay: float = 2.0):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = base_url or settings.LLM_BASE_URL
        self.model = model or settings.LLM_MODEL
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout
        )

    def generate(self, system_prompt: str, user_prompt: str,
                 temperature: float = 0.7,
                 max_tokens: int = 2000) -> str:
        """
        生成文本（带指数退避重试）

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            生成的文本
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens
                )

                return response.choices[0].message.content

            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"⚠️  LLM调用失败 (尝试 {attempt}/{self.max_retries}): {e}"
                    )
                    logger.info(f"⏳ {wait_time:.1f}秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"❌ LLM调用失败，已重试 {self.max_retries} 次: {e}"
                    )

        raise Exception(
            f"LLM调用失败，已重试 {self.max_retries} 次: {last_error}"
        )

    def is_available(self) -> bool:
        """检查LLM服务是否可用"""
        return bool(self.api_key)
