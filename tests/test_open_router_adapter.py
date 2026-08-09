from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from openai import APIStatusError

from app.adapters.open_router import OpenRouterAdapter


def fake_response(content="hi"):
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice])


def fake_status_error(status_code: int) -> APIStatusError:
    request = MagicMock()
    response = MagicMock(status_code=status_code, headers={})
    return APIStatusError("blocked", response=response, body={"error": {"message": "blocked"}})


def make_adapter() -> OpenRouterAdapter:
    return OpenRouterAdapter(api_key="test-key", model="openrouter/auto", fallback_model="fallback/free")


def test_chat_uses_primary_model_on_success():
    adapter = make_adapter()
    adapter._client.chat.completions.create = MagicMock(return_value=fake_response("hello"))

    result = adapter.chat([{"role": "user", "content": "hi"}])

    assert result.text == "hello"
    adapter._client.chat.completions.create.assert_called_once()
    assert adapter._client.chat.completions.create.call_args.kwargs["model"] == "openrouter/auto"


@pytest.mark.parametrize("status_code", [402, 403])
def test_chat_falls_back_on_billing_errors(status_code):
    adapter = make_adapter()
    adapter._client.chat.completions.create = MagicMock(
        side_effect=[fake_status_error(status_code), fake_response("fallback reply")]
    )

    result = adapter.chat([{"role": "user", "content": "hi"}])

    assert result.text == "fallback reply"
    assert adapter._client.chat.completions.create.call_count == 2
    second_call_model = adapter._client.chat.completions.create.call_args_list[1].kwargs["model"]
    assert second_call_model == "fallback/free"


def test_chat_reraises_non_billing_errors():
    adapter = make_adapter()
    adapter._client.chat.completions.create = MagicMock(side_effect=fake_status_error(500))

    with pytest.raises(APIStatusError):
        adapter.chat([{"role": "user", "content": "hi"}])


def test_chat_falls_back_on_empty_response():
    adapter = make_adapter()
    adapter._client.chat.completions.create = MagicMock(
        side_effect=[fake_response(content=None), fake_response("fallback reply")]
    )

    result = adapter.chat([{"role": "user", "content": "hi"}])

    assert result.text == "fallback reply"
    assert adapter._client.chat.completions.create.call_count == 2


def test_chat_raises_when_fallback_also_returns_empty():
    adapter = make_adapter()
    adapter._client.chat.completions.create = MagicMock(return_value=fake_response(content=None))

    with pytest.raises(ValueError):
        adapter.chat([{"role": "user", "content": "hi"}])
