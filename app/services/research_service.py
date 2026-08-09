import json
import logging

from app.adapters.espn_rss import EspnRssAdapter
from app.adapters.llm import LLMAdapter
from app.models.news import MaterialityAssessment, NewsItem

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You triage NFL news for a fantasy football manager. \
For each headline, decide whether it's MATERIAL — it shifts a player's fantasy \
value or role (trade, injury, depth chart change, suspension, retirement, \
coaching change affecting scheme) — versus routine coverage (previews, \
recaps, general storylines, opinion pieces) which is NOT material.

Respond with ONLY a JSON array, one object per headline in the same order, \
each shaped exactly as: {"material": true|false, "reason": "<one sentence>"}. \
No other text."""


class ResearchService:
    def __init__(self, news_adapter: EspnRssAdapter, llm: LLMAdapter):
        self._news_adapter = news_adapter
        self._llm = llm

    def get_materiality_feed(self, limit: int = 25) -> list[MaterialityAssessment]:
        items = self._news_adapter.fetch(limit=limit)
        if not items:
            return []
        return self._assess(items)

    def _assess(self, items: list[NewsItem]) -> list[MaterialityAssessment]:
        headlines = "\n".join(f"{i}. {item.title} — {item.summary}" for i, item in enumerate(items))
        result = self._llm.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": headlines},
            ]
        )
        try:
            verdicts = json.loads(_strip_code_fence(result.text))
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse materiality response, marking all unassessed: %r", result.text)
            verdicts = [{"material": False, "reason": "Materiality assessment failed to parse"} for _ in items]

        assessments = []
        for item, verdict in zip(items, verdicts):
            assessments.append(
                MaterialityAssessment(
                    item=item,
                    material=bool(verdict.get("material", False)),
                    reason=str(verdict.get("reason", "")),
                )
            )
        return assessments


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()
