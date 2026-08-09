import logging

from openai import APIStatusError, OpenAI

from app.adapters.llm import LLMAdapter, LLMResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"

# 402 = insufficient credits; 403 = OpenRouter key-level spend limit hit.
# Both mean "can't use a paid model right now" — fall back rather than fail.
_BILLING_BLOCKED_STATUS_CODES = {402, 403}


class OpenRouterAdapter(LLMAdapter):
    def __init__(self, api_key: str, model: str, fallback_model: str):
        self._model = model
        self._fallback_model = fallback_model
        self._client = OpenAI(api_key=api_key, base_url=_BASE_URL)

    def chat(self, messages: list[dict]) -> LLMResult:
        try:
            return self._chat_with(self._model, messages)
        except APIStatusError as e:
            if e.status_code not in _BILLING_BLOCKED_STATUS_CODES:
                raise
            logger.warning(
                "OpenRouter model %s blocked (HTTP %d: %s), falling back to %s",
                self._model,
                e.status_code,
                e.message,
                self._fallback_model,
            )
            return self._chat_with(self._fallback_model, messages)

    def _chat_with(self, model: str, messages: list[dict]) -> LLMResult:
        logger.debug("Sending %d messages to OpenRouter model %s", len(messages), model)
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2048,
        )
        if not response.choices or not response.choices[0].message.content:
            finish_reason = repr(response.choices[0].finish_reason) if response.choices else "no choices"
            raise ValueError(f"Empty response from model {model} (finish_reason={finish_reason})")
        return LLMResult(text=response.choices[0].message.content)
