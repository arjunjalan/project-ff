from app.adapters.llm import LLMAdapter, LLMResult
from app.models.news import NewsItem
from app.services.research_service import ResearchService


class FakeNewsAdapter:
    def __init__(self, items: list[NewsItem]):
        self._items = items

    def fetch(self, limit: int = 25) -> list[NewsItem]:
        return self._items[:limit]


class FakeLLM(LLMAdapter):
    def __init__(self, response_text: str):
        self._response_text = response_text

    def chat(self, messages: list[dict]) -> LLMResult:
        return LLMResult(text=self._response_text)


def make_item(title="Some headline"):
    return NewsItem(title=title, summary="summary", link="https://example.com")


def test_get_materiality_feed_parses_verdicts_in_order():
    items = [make_item("Player traded"), make_item("Season preview roundup")]
    llm = FakeLLM('[{"material": true, "reason": "trade shifts role"}, {"material": false, "reason": "routine recap"}]')
    service = ResearchService(FakeNewsAdapter(items), llm)

    results = service.get_materiality_feed()

    assert len(results) == 2
    assert results[0].material is True
    assert results[0].reason == "trade shifts role"
    assert results[1].material is False


def test_get_materiality_feed_handles_code_fenced_json():
    items = [make_item()]
    llm = FakeLLM('```json\n[{"material": false, "reason": "n/a"}]\n```')
    service = ResearchService(FakeNewsAdapter(items), llm)

    results = service.get_materiality_feed()

    assert results[0].material is False


def test_get_materiality_feed_falls_back_on_unparseable_response():
    items = [make_item()]
    llm = FakeLLM("not json at all")
    service = ResearchService(FakeNewsAdapter(items), llm)

    results = service.get_materiality_feed()

    assert len(results) == 1
    assert results[0].material is False


def test_get_materiality_feed_empty_news_skips_llm_call():
    class ExplodingLLM(LLMAdapter):
        def chat(self, messages: list[dict]) -> LLMResult:
            raise AssertionError("should not be called")

    service = ResearchService(FakeNewsAdapter([]), ExplodingLLM())

    assert service.get_materiality_feed() == []
