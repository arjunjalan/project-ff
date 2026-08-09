from app.adapters.llm import LLMAdapter
from app.models.league import League, LeagueSettings
from app.models.strategy import StrategyBrief
from app.services.league_settings_summary import summarize_settings
from app.services.research_service import ResearchService
from app.services.retrospective_service import RetrospectiveService
from app.storage.store import Store

# Arjun's draft slot per season (1-indexed, snake draft) — no ESPN field carries this
# (it's assigned live at draft time), so it's tracked here by hand. Add next year's
# entry once the slot is known; omitted years just get a brief with no pick-position
# reasoning.
_DRAFT_SLOTS: dict[int, int] = {2026: 8}

_SYSTEM_PROMPT = """You're a fantasy football advisor building a personal draft strategy \
brief for a manager, ahead of their upcoming draft. You'll get: this league's actual \
scoring/roster rules, the manager's own draft slot and upcoming pick numbers (if known), \
a retrospective narrative on the manager's own last-season draft (if available) plus that \
retrospective's raw position-by-position breakdown (points and rate aggregated per position \
— the same numbers the retrospective itself used, not a re-summary of it), and current \
materiality-filtered NFL news (if available).

Write a short strategy brief (5-8 sentences) that:
- Names 1-2 concrete roster-construction priorities specific to THIS league's rules \
(e.g. how PPR and the flex/bench setup should shape when to draft each position) — not \
generic advice that ignores the settings given.
- If a draft slot and pick list are provided, reason about pick position explicitly — e.g. \
whether to expect a run on a scarce position before the next pick comes back around, or \
whether the gap between consecutive picks favors reaching for a positional need now vs. \
waiting. Don't just restate the pick numbers without using them to shape a recommendation. \
If no draft slot is provided, don't invent one or assume a specific pick position.
- If a position breakdown is provided, use the actual numbers in it to justify at least one \
recommendation directly (e.g. "RB returned only ~11.6 pts/started-week on early picks last \
year against QB's ~25.8 — don't assume more early RB investment fixes that without a reason \
to expect this year's RB pool differs"). Don't just gesture at "roster construction lessons" \
in the abstract when you have real numbers to cite.
- If a retrospective narrative is provided, carry forward 1-2 lessons from it — but distinguish \
lessons about genuine value picks (late-round players who outproduced their slot — those \
patterns are worth hunting for again) from lessons about early-round investments that simply \
paid off (those aren't a repeatable "value" strategy, they're a scarcity/certainty bet — say so \
if the narrative frames it that way).
- If the scoring format changed between last season and this one (flagged explicitly in \
the input if so), say plainly which retrospective lessons about position value still \
apply and which don't transfer directly — e.g. a non-PPR-to-PPR change raises WR/pass-\
catcher value, so "avoid early WRs" from a non-PPR retrospective needs re-checking, not \
blind carry-forward.
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

        settings_summary = summarize_settings(league.settings)

        try:
            retro = self._retrospective_service.get_retrospective(year - 1)
        except ValueError:
            retro = None

        prior_league = self._store.load(f"league_{year - 1}", League)
        scoring_change_note = _scoring_change_note(prior_league, league)

        news = self._research_service.get_materiality_feed(limit=15)
        material_news = [a for a in news if a.material]

        draft_slot = _DRAFT_SLOTS.get(year)
        pick_numbers = _snake_picks(draft_slot, league.settings) if draft_slot else None

        narrative = self._synthesize(settings_summary, retro, material_news, scoring_change_note, draft_slot, pick_numbers)

        return StrategyBrief(
            year=year,
            league_settings_summary=settings_summary,
            narrative=narrative,
            draft_slot=draft_slot,
        )

    def _synthesize(self, settings_summary, retro, material_news, scoring_change_note, draft_slot, pick_numbers) -> str:
        lines = [f"This season's league settings: {settings_summary}"]

        if draft_slot:
            lines.append(
                f"\nManager's draft slot: {draft_slot}. Upcoming picks (snake draft): "
                f"{', '.join(str(p) for p in pick_numbers)}."
            )
        else:
            lines.append("\nNo draft slot recorded for this season — omit pick-position reasoning.")

        if scoring_change_note:
            lines.append(f"\nSCORING FORMAT CHANGE: {scoring_change_note}")

        if retro is not None:
            lines.append(f"\nLast season's retrospective ({retro.team_name}, {retro.wins}-{retro.losses}):")
            lines.append(retro.narrative)
            if retro.position_breakdown:
                lines.append("\nLast season's position-by-position breakdown (raw numbers, not the narrative's summary of them):")
                lines.extend(retro.position_breakdown)
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


def _snake_picks(draft_slot: int, settings: LeagueSettings) -> list[int]:
    team_count = settings.team_count
    rounds = sum(settings.position_slot_counts.values())
    picks = []
    for r in range(1, rounds + 1):
        slot_in_round = draft_slot if r % 2 == 1 else team_count - draft_slot + 1
        picks.append((r - 1) * team_count + slot_in_round)
    return picks


def _scoring_change_note(prior_league: League | None, current_league: League) -> str | None:
    if prior_league is None or prior_league.settings is None or current_league.settings is None:
        return None
    prior = prior_league.settings
    current = current_league.settings
    if prior.points_per_reception != current.points_per_reception:
        return (
            f"points-per-reception changed from {prior.points_per_reception} "
            f"({prior_league.year}) to {current.points_per_reception} ({current_league.year})."
        )
    return None
