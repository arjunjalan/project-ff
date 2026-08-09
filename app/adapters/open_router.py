import logging

from openai import OpenAI

from app.adapters.llm import LLMAdapter, LLMResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterAdapter(LLMAdapter):
    def __init__(self, api_key: str, model: str):
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=_BASE_URL)

    def chat(self, messages: list[dict]) -> LLMResult:
        logger.debug("Sending %d messages to OpenRouter model %s", len(messages), self._model)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=2048,
        )
        if not response.choices or not response.choices[0].message.content:
            finish_reason = repr(response.choices[0].finish_reason) if response.choices else "no choices"
            raise ValueError(f"Empty response from model (finish_reason={finish_reason})")
        return LLMResult(text=response.choices[0].message.content)
