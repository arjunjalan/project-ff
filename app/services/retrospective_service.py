from app.adapters.llm import LLMAdapter
from app.models.league import DraftPick, League, Team
from app.models.retrospective import TeamRetrospective
from app.services.league_settings_summary import summarize_settings
from app.storage.store import Store

_BENCH_SLOTS = {"BE", "IR"}

_SYSTEM_PROMPT = """You're a fantasy football advisor helping a manager learn from last \
season's draft. You'll get that season's actual scoring rules (e.g. PPR or not) — interpret \
every pick's production in light of those rules, not generic assumptions. For example, a \
receiver's total looks very different under non-PPR than PPR; don't judge a pick as weak \
just because a receiver-type player scored low if the league was non-PPR that season.

For each pick you'll get: round/pick, player, position, how many weeks of the season they \
were on this specific roster, how many of those weeks they were started (not benched/IR), \
their total points while on this roster, and their points-per-week rate while started. Some \
picks are marked as never having appeared in a weekly lineup for this team — for those, \
production on this roster is genuinely unknown; do not guess, do not call them a bust, just \
note the pick and move on.

Write a short retrospective (4-6 sentences) that:
- Judges value primarily by points-per-started-week rate, not season total — a full-season \
starter and a 3-week rental with a similar total are very different outcomes, and the \
retrospective should say so explicitly when it applies.
- Names the single best-value pick (weigh both a strong rate AND meaningful weeks-started \
coverage — a great rate over only 1-2 weeks is a small sample, not a proven value pick) and \
the single biggest bust (an early pick with a weak rate despite being started regularly), \
citing round/pick, weeks started, and the rate.
- If a highly-drafted player was rostered most/all of the season but started only a fraction \
of those weeks, call that out explicitly — it's a real signal (injury, poor performance, or a \
roster crunch) distinct from the points-per-week rate alone.
- Identifies 1-2 concrete roster-construction patterns worth repeating or avoiding next draft.

Ground every claim in the specific picks/numbers given — no generic advice."""


class RetrospectiveService:
    def __init__(self, store: Store, llm: LLMAdapter):
        self._store = store
        self._llm = llm

    def get_retrospective(self, year: int) -> TeamRetrospective | None:
        cache_key = f"retrospective_{year}"
        cached = self._store.load(cache_key, TeamRetrospective)
        if cached is not None:
            return cached

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

        narrative = self._narrate(my_team, my_picks, league.settings)

        retrospective = TeamRetrospective(
            team_name=my_team.name,
            year=year,
            wins=my_team.wins,
            losses=my_team.losses,
            final_standing=my_team.final_standing,
            picks=my_picks,
            narrative=narrative,
        )
        self._store.save(cache_key, retrospective)
        return retrospective

    def _narrate(self, team: Team, picks: list[DraftPick], settings) -> str:
        if not picks:
            return "No draft picks found for this team in the synced data."

        lines = [f"Record: {team.wins}-{team.losses}, final standing {team.final_standing}"]
        if settings is not None:
            lines.append(f"Scoring rules that season: {summarize_settings(settings)}")
        for p in picks:
            lines.append(f"Round {p.round_num}, Pick {p.round_pick}: {p.player.name} ({p.player.position}) — {_pick_line(p)}")
        result = self._llm.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": "\n".join(lines)},
            ]
        )
        return result.text


def _pick_line(pick: DraftPick) -> str:
    weekly = pick.player.weekly
    if not weekly:
        return "never appeared in a weekly lineup for this team — production on this roster is unknown, likely cut/traded before Week 1"

    weeks_started = [w for w in weekly if w.slot not in _BENCH_SLOTS]
    total = pick.player.total_points
    rate = total / len(weeks_started) if weeks_started else 0.0
    return (
        f"on roster {len(weekly)} of the season's weeks, started {len(weeks_started)} of them, "
        f"{total:.1f} pts total (~{rate:.1f} pts/week while started)"
    )
