from collections import defaultdict

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

For each pick you'll get: round/pick, player, position, an (early-round pick) or (late-round \
pick) tag (split at the draft's halfway point), how many weeks of the season they were on \
this specific roster, how many of those weeks they were started (not benched/IR), their total \
points while on this roster, and their points-per-week rate while started. Some picks are \
marked as never having appeared in a weekly lineup for this team — for those, production on \
this roster is genuinely unknown; do not guess, do not call them a bust, just note the pick \
and move on.

CRITICAL — "value" means something specific here, don't use it loosely:
- A pick only earns the word "value" if it's tagged (late-round pick) AND it meaningfully \
outproduced what that draft slot normally returns. Getting a good player late is value \
because the opportunity cost was low.
- An (early-round pick) that performed well is NOT "value" — it's expected. Early picks, \
especially at premium/scarce positions (elite QB, elite TE), are often a deliberate choice \
to lock in a top performer with certainty rather than risk losing him to another team — call \
that "a justified early investment" or "paid off as intended," and the real question worth \
asking is whether the opportunity cost (what a different position could have returned at \
that same early slot) was worth it, not whether the player himself was good.
- Never call a top-of-position performer (e.g. the league's #1 QB) "value" just because his \
rate is the highest number on the roster — high raw production from an early, premium-\
position pick is the point of drafting him there, not a market inefficiency.

You'll also get a position-by-position breakdown (total points and points-per-started-week \
rate, aggregated across every pick at that position). Use it to discuss roster construction \
directly — e.g. whether points returned per position roughly matched the draft capital (round \
number, pick count) invested there, and whether the mix across positions looks efficient.

Write a short retrospective (5-7 sentences) that:
- Names the single genuine value pick per the definition above (late-round, outproduced \
its slot) — if no pick qualifies, say so explicitly rather than forcing one.
- Separately discusses the team's best early-round investment and whether its opportunity \
cost (draft capital spent at that position/round) looks justified based on the position \
breakdown.
- Names the single biggest bust (an early pick with a weak rate despite being started \
regularly), citing round/pick, weeks started, and the rate.
- Comments on the position-by-position breakdown directly — which position group returned \
the most/least relative to picks invested there, and whether that suggests a pattern to \
repeat or avoid next draft.
- If a highly-drafted player was rostered most/all of the season but started only a fraction \
of those weeks, call that out explicitly — it's a real signal (injury, poor performance, or a \
roster crunch) distinct from the rate alone.

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

        max_round = max(p.round_num for p in picks)
        midpoint = max_round / 2

        lines = [f"Record: {team.wins}-{team.losses}, final standing {team.final_standing}"]
        if settings is not None:
            lines.append(f"Scoring rules that season: {summarize_settings(settings)}")
        lines.append(f"Draft had {max_round} rounds; picks in rounds 1-{midpoint:.0f} are (early-round), the rest (late-round).")

        lines.append("\nPicks:")
        for p in picks:
            era = "early-round" if p.round_num <= midpoint else "late-round"
            lines.append(
                f"Round {p.round_num}, Pick {p.round_pick} ({era}): {p.player.name} "
                f"({p.player.position}) — {_pick_line(p)}"
            )

        lines.append("\nPosition breakdown (aggregated across all picks at that position):")
        lines.extend(_position_breakdown(picks))

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


def _position_breakdown(picks: list[DraftPick]) -> list[str]:
    groups: dict[str, list[DraftPick]] = defaultdict(list)
    for p in picks:
        groups[p.player.position or "Unknown"].append(p)

    lines = []
    for position, group_picks in sorted(groups.items()):
        total_points = sum(p.player.total_points for p in group_picks)
        weeks_started = sum(
            len([w for w in p.player.weekly if w.slot not in _BENCH_SLOTS]) for p in group_picks
        )
        rate = total_points / weeks_started if weeks_started else 0.0
        lines.append(
            f"{position}: {len(group_picks)} pick(s), {total_points:.1f} pts total, "
            f"{weeks_started} started-weeks, ~{rate:.1f} pts/started-week"
        )
    return lines
