from app.adapters.llm import LLMAdapter
from app.models.league import DraftPick, League, Team
from app.models.retrospective import TeamRetrospective
from app.storage.store import Store

_SYSTEM_PROMPT = """You're a fantasy football advisor helping a manager learn from last \
season's draft. You'll get their team's record and every pick they made, with round, \
pick number, player, position, and the fantasy points that player scored while on this \
roster that season.

IMPORTANT: a pick showing 0 points and a blank position means the player was traded or \
dropped off this roster before the data was captured — it does NOT mean they scored zero \
or were a bust. Never call a 0-point pick a "bust"; note it separately as "left the roster \
mid-season, production unknown" if it's worth mentioning at all.

Write a short retrospective (4-6 sentences) that:
- Among picks with real point totals, names the single best-value pick (a late pick that \
scored like an early one) and the single biggest bust (an early pick that scored like a \
late one), citing round/pick and points.
- Identifies 1-2 concrete roster-construction patterns worth repeating or avoiding next \
draft (e.g. positions drafted too early/late relative to how they scored).

Ground every claim in the specific picks/numbers given — no generic advice."""


class RetrospectiveService:
    def __init__(self, store: Store, llm: LLMAdapter):
        self._store = store
        self._llm = llm

    def get_retrospective(self, year: int) -> TeamRetrospective | None:
        league = self._store.load(f"league_{year}", League)
        if league is None:
            return None

        my_team = next((t for t in league.teams if t.is_mine), None)
        if my_team is None:
            raise ValueError(f"No team owned by the configured ESPN account found in {year} league data")

        my_picks = sorted(
            (p for p in league.draft if p.team_espn_id == my_team.espn_id),
            key=lambda p: (p.round_num, p.round_pick),
        )

        narrative = self._narrate(my_team, my_picks)

        return TeamRetrospective(
            team_name=my_team.name,
            year=year,
            wins=my_team.wins,
            losses=my_team.losses,
            final_standing=my_team.final_standing,
            picks=my_picks,
            narrative=narrative,
        )

    def _narrate(self, team: Team, picks: list[DraftPick]) -> str:
        if not picks:
            return "No draft picks found for this team in the synced data."

        lines = [f"Record: {team.wins}-{team.losses}, final standing {team.final_standing}"]
        for p in picks:
            lines.append(
                f"Round {p.round_num}, Pick {p.round_pick}: {p.player.name} "
                f"({p.player.position}) — {p.player.total_points} pts"
            )
        result = self._llm.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": "\n".join(lines)},
            ]
        )
        return result.text
