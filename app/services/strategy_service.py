from app.adapters.llm import LLMAdapter
from app.models.league import League, LeagueSettings
from app.models.strategy import StrategyBrief
from app.services.research_service import ResearchService
from app.services.retrospective_service import RetrospectiveService
from app.storage.store import Store

_SYSTEM_PROMPT = """You're a fantasy football advisor building a personal draft strategy \
brief for a manager, ahead of their upcoming draft. You'll get: this league's actual \
scoring/roster rules, a retrospective on the manager's own last-season draft (if \
available), and current materiality-filtered NFL news (if available).

Write a short strategy brief (5-8 sentences) that:
- Names 1-2 concrete roster-construction priorities specific to THIS league's rules \
(e.g. how PPR and the flex/bench setup should shape when to draft each position) — not \
generic advice that ignores the settings given.
- If a retrospective is provided, explicitly carries forward 1-2 lessons from it (e.g. \
"last year you drafted RBs too early relative to how they scored — this year...").
- If current news is provided, names any player/situation from it worth targeting or \
avoiding, citing the specific news item.
- If retrospective or news data is missing or thin, say so plainly rather than inventing \
specifics — do not fabricate rankings, player values, or news that wasn't given to you."""


class StrategyService:
    def __init__(
        self,
        store: Store,
        llm: LLMAdapter,
        retrospective_service: RetrospectiveService,
        research_service: ResearchService,
    ):
        self._store = store
        self._llm = llm
        self._retrospective_service = retrospective_service
        self._research_service = research_service

    def get_strategy(self, year: int) -> StrategyBrief | None:
        league = self._store.load(f"league_{year}", League)
        if league is None or league.settings is None:
            return None

        settings_summary = _summarize_settings(league.settings)

        try:
            retro = self._retrospective_service.get_retrospective(year - 1)
        except ValueError:
            retro = None

        news = self._research_service.get_materiality_feed(limit=15)
        material_news = [a for a in news if a.material]

        narrative = self._synthesize(settings_summary, retro, material_news)

        return StrategyBrief(year=year, league_settings_summary=settings_summary, narrative=narrative)

    def _synthesize(self, settings_summary, retro, material_news) -> str:
        lines = [f"League settings: {settings_summary}"]

        if retro is not None:
            lines.append(f"\nLast season's retrospective ({retro.team_name}, {retro.wins}-{retro.losses}):")
            lines.append(retro.narrative)
        else:
            lines.append("\nNo retrospective available (prior season not synced).")

        if material_news:
            lines.append("\nCurrent materiality-filtered news:")
            for a in material_news:
                lines.append(f"- {a.item.title}: {a.reason}")
        else:
            lines.append("\nNo current material news available.")

        result = self._llm.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": "\n".join(lines)},
            ]
        )
        return result.text


def _summarize_settings(s: LeagueSettings) -> str:
    starters = {k: v for k, v in s.position_slot_counts.items() if k not in ("BE", "IR")}
    starters_str = ", ".join(f"{v} {k}" for k, v in starters.items())
    return (
        f"{s.team_count}-team {s.scoring_type}, {s.points_per_reception} pt/reception, "
        f"starters: {starters_str}, playoff teams: {s.playoff_team_count}, keepers: {s.keeper_count}"
    )
