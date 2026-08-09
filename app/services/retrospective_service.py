from collections import defaultdict

from app.adapters.llm import LLMAdapter
from app.models.league import DraftPick, League, PositionRanking, Team, Transaction
from app.models.retrospective import TeamRetrospective
from app.services.league_settings_summary import summarize_settings
from app.storage.store import Store

_BENCH_SLOTS = {"BE", "IR"}
_FLEX_SLOT = "RB/WR/TE"
_FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}
_MULTI_SLOT_POSITIONS = {"RB", "WR"}  # this league starts 2 of each — needs a 1/2 split
_SINGLE_SLOT_POSITIONS = {"QB", "TE", "D/ST", "K"}

# How good a season-long positional finish has to be for a pick at that
# role to be considered to have "mattered" — Arjun's tiers, anchored to
# replacement value: a QB1 not top-3 is replaceable by streaming, a WR2
# has more slack than a WR1, etc.
_TIER_THRESHOLDS = {"QB": 3, "RB1": 5, "RB2": 12, "WR1": 5, "WR2": 12, "TE": 5, "D/ST": 5, "K": 5}
_FLEX_THRESHOLDS = {"RB": 20, "WR": 20, "TE": 10}

_SYSTEM_PROMPT = """You're a fantasy football advisor helping a manager learn from last \
season's draft. You'll get that season's actual scoring rules (e.g. PPR or not) — interpret \
every pick's production in light of those rules, not generic assumptions.

For each pick you'll get: round/pick, player, position, an (early-round pick) or (late-round \
pick) tag (split at the draft's halfway point), the ROLE they actually played on this roster \
(QB / RB1 / RB2 / WR1 / WR2 / TE / FLEX / D/ST / K / BENCH, assigned by which lineup slot they \
were actually started in most), and — this is the key signal — whether they CLEARED or MISSED \
the season-long positional finish bar for that role (e.g. a WR1 needed to finish top-5 among \
all WRs that season to really matter; a WR2 only needed top-12; FLEX-RB/WR needed top-20, \
FLEX-TE top-10). This is a real, computed finish rank against every player at that position \
that season under this league's scoring — not a guess. You'll also get weeks-on-roster/\
weeks-started/points-per-started-week as secondary color for roster-management quality (did \
the manager actually start their good players). Some picks are marked as never having \
appeared in a weekly lineup — production on this roster is genuinely unknown for those; do \
not guess, do not call them a bust, just note the pick and move on. Picks marked BENCH never \
started at that position — no tier bar applies to them.

CRITICAL — use the tier bar as the primary signal, not raw points or rate:
- A genuine "value" pick is a (late-round pick) whose role CLEARED its bar — real starter-\
level production for low draft-capital cost.
- A genuine "bust" is an (early-round pick) whose role MISSED its bar — premium draft capital \
that didn't return starter-level production at that role. This is different from, and more \
useful than, "low points" alone.
- An (early-round pick) whose role CLEARED its bar is NOT "value" and NOT automatically \
praiseworthy either — it's the expected outcome for early draft capital. Call it "a justified \
early investment," and note whether the opportunity cost (what else that draft slot could \
have returned) looks reasonable given the position breakdown.
- Never call a top-of-position performer "value" just because his raw rate is the highest \
number on the roster.

You'll also get a position-by-position breakdown (total points and points-per-started-week \
rate, aggregated across every pick at that position). Use it to discuss roster construction \
directly — e.g. whether points returned per position roughly matched the draft capital \
invested there.

You may also get a season waiver-wire activity summary (executed adds/drops, FAAB spent, any \
standout free-agent pickups). If given, weave a brief comment about it into the roster-\
construction picture — e.g. a free-agent pickup that outproduced a bench draft pick is a real \
signal about in-season management, separate from draft quality. A "Bench stash" line means a \
good waiver add that mostly sat on the bench — report this as a fact, not a verdict. Do NOT \
call it a mistake or mismanagement: rostering a strong backup behind an established starter, \
especially at a scarce/thin position, is often a deliberate insurance or scarcity play (protects \
against the starter's bye/injury, denies a good player to rivals), not an oversight. If you \
mention it, frame it as "X was stashed behind Y" or similar, and it's fine to note the plausible \
strategic rationale rather than assuming it was wasted. Don't invent activity beyond what's \
listed, and don't force a comment if the summary is empty or unremarkable.

Write a short retrospective (6-8 sentences) that:
- Leads with which starting roles cleared their tier bar and which didn't, naming the roles \
specifically (e.g. "QB cleared comfortably, WR2 missed badly").
- Names the single genuine value pick per the definition above — if none qualifies, say so \
explicitly rather than forcing one.
- Names the single biggest bust per the definition above — if none qualifies (no early pick \
missed its bar), say so explicitly.
- Separately names the team's best early-round investment (cleared its bar) and whether its \
opportunity cost looks justified, using the position breakdown.
- Comments on the position-by-position breakdown directly — which position group returned \
the most/least relative to picks invested there.
- If a highly-drafted player was rostered most/all of the season but started only a fraction \
of those weeks, call that out — it's a real signal (injury, poor performance, or a roster \
crunch) distinct from the tier result alone.

Ground every claim in the specific picks/roles/tiers given — no generic advice."""


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

        position_breakdown = _position_breakdown(my_picks) if my_picks else []
        transaction_summary = _transaction_summary(my_team, league.transactions)
        narrative = self._narrate(
            my_team, my_picks, league.settings, position_breakdown, league.positional_rankings, transaction_summary
        )

        retrospective = TeamRetrospective(
            team_name=my_team.name,
            year=year,
            wins=my_team.wins,
            losses=my_team.losses,
            final_standing=my_team.final_standing,
            picks=my_picks,
            narrative=narrative,
            position_breakdown=position_breakdown,
            transaction_summary=transaction_summary,
        )
        self._store.save(cache_key, retrospective)
        return retrospective

    def _narrate(
        self,
        team: Team,
        picks: list[DraftPick],
        settings,
        position_breakdown: list[str],
        positional_rankings: dict[str, list[PositionRanking]],
        transaction_summary: list[str],
    ) -> str:
        if not picks:
            return "No draft picks found for this team in the synced data."

        max_round = max(p.round_num for p in picks)
        midpoint = max_round / 2
        roles = _assign_roles(picks)

        lines = [f"Record: {team.wins}-{team.losses}, final standing {team.final_standing}"]
        if settings is not None:
            lines.append(f"Scoring rules that season: {summarize_settings(settings)}")
        lines.append(f"Draft had {max_round} rounds; picks in rounds 1-{midpoint:.0f} are (early-round), the rest (late-round).")

        lines.append("\nPicks:")
        for p in picks:
            era = "early-round" if p.round_num <= midpoint else "late-round"
            role = roles.get(p.player.espn_id)
            lines.append(
                f"Round {p.round_num}, Pick {p.round_pick} ({era}): {p.player.name} "
                f"({p.player.position}) — {_tier_line(p, role, positional_rankings)}; {_pick_line(p)}"
            )

        lines.append("\nPosition breakdown (aggregated across all picks at that position):")
        lines.extend(position_breakdown)

        if transaction_summary:
            lines.append("\nSeason waiver-wire activity:")
            lines.extend(transaction_summary)

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


# Floor for flagging a "bench stash" worth surfacing at all — not just scrub
# production that happened to accumulate on the bench (e.g. a single
# 6-point flex-eligible bench week isn't a real signal, a sustained double-
# digit rate is).
_UNDERUSED_BENCH_RATE_FLOOR = 10.0


def _transaction_summary(team: Team, transactions: list[Transaction]) -> list[str]:
    """Season-long waiver/free-agent activity for one team: executed move
    counts, FAAB spent, standout pickups, and "bench stash" pickups that
    produced well but were rarely started. Empty transactions means either
    an unsynced/pre-#11 dataset or genuinely no activity — either way
    there's nothing useful to say.

    Points are always split by started vs. benched weeks. Mixing the two
    (e.g. a raw season total next to a "started weeks" count) misrepresents
    a player who mostly sat the bench as a highly efficient starter — a real
    bug caught by Arjun spot-checking Drake Maye's numbers: his 162.9-point
    season total looked like a great return over "2 started weeks" (~81
    pts/week), but 7 of his 9 weeks on the roster were actually spent on the
    bench, most of them scoring 15-27 points unstarted.

    Deliberately doesn't call this a "mistake": Arjun pushed back on that
    framing directly — a strong QB2 sat behind an elite QB1 can be
    legitimate insurance (bye/injury) or a deliberate scarcity play (deny a
    good backup to rivals in a shallow-QB league), not necessarily a missed
    start. The data can't distinguish those cases from an actual oversight,
    so it's reported as a fact for the LLM (and Arjun) to interpret, not a
    verdict.
    """
    executed = [t for t in transactions if t.team_espn_id == team.espn_id and t.status == "EXECUTED"]
    if not executed:
        return []

    # A player added more than once (add/drop/re-add) should only be
    # reported once — weekly data covers their whole tenure on this roster
    # regardless of which transaction it's attached to.
    adds_by_player = {}
    drop_count = 0
    for t in executed:
        for i in t.items:
            if i.action == "ADD":
                adds_by_player[i.player.espn_id] = i.player
            elif i.action == "DROP":
                drop_count += 1
    faab_spent = sum(t.bid_amount for t in executed if t.type == "WAIVER")

    lines = [
        f"{len(executed)} executed moves this season: {len(adds_by_player)} unique players added, "
        f"{drop_count} drops, ${faab_spent:.0f} FAAB spent"
    ]

    stats = []
    for player in adds_by_player.values():
        if not player.weekly:
            continue
        started = [w for w in player.weekly if w.slot not in _BENCH_SLOTS]
        benched = [w for w in player.weekly if w.slot in _BENCH_SLOTS]
        stats.append(
            (
                player,
                len(started),
                len(benched),
                sum(w.points for w in started),
                sum(w.points for w in benched),
            )
        )

    productive = sorted((s for s in stats if s[3] > 0), key=lambda s: -s[3])
    for player, weeks_started, _weeks_benched, started_points, _benched_points in productive[:3]:
        lines.append(
            f"Notable pickup: {player.name} ({player.position}) — {started_points:.1f} pts "
            f"across {weeks_started} started weeks after being added"
        )

    underused = sorted(
        (s for s in stats if s[2] > s[1] and s[2] > 0 and (s[4] / s[2]) >= _UNDERUSED_BENCH_RATE_FLOOR),
        key=lambda s: -s[4],
    )
    for player, weeks_started, weeks_benched, _started_points, benched_points in underused[:2]:
        bench_rate = benched_points / weeks_benched
        lines.append(
            f"Bench stash: {player.name} ({player.position}) — added but started only "
            f"{weeks_started} of {weeks_started + weeks_benched} weeks on the roster despite averaging "
            f"{bench_rate:.1f} pts/week while benched"
        )

    return lines


def _started_weeks_in_slot(pick: DraftPick, slot: str) -> int:
    return len([w for w in pick.player.weekly if w.slot == slot])


def _assign_roles(picks: list[DraftPick]) -> dict[int, str]:
    """Map each pick's player to the role they actually played: QB, RB1/RB2,
    WR1/WR2, TE, D/ST, K, FLEX, or BENCH (drafted but never actually started
    at their position). Based on which lineup slot they were started in most,
    not draft order — a player drafted first isn't "RB1" if the other RB
    played there more.
    """
    flex_candidates = [
        (p, _started_weeks_in_slot(p, _FLEX_SLOT)) for p in picks if p.player.position in _FLEX_ELIGIBLE_POSITIONS
    ]
    flex_candidates = [c for c in flex_candidates if c[1] > 0]
    flex_candidates.sort(key=lambda c: -c[1])
    flex_pick = flex_candidates[0][0] if flex_candidates else None

    roles: dict[int, str] = {}
    if flex_pick is not None:
        roles[flex_pick.player.espn_id] = "FLEX"

    by_position: dict[str, list[DraftPick]] = defaultdict(list)
    for p in picks:
        if flex_pick is not None and p.player.espn_id == flex_pick.player.espn_id:
            continue
        by_position[p.player.position].append(p)

    for position, group in by_position.items():
        if position in _SINGLE_SLOT_POSITIONS:
            for p in group:
                roles[p.player.espn_id] = position if _started_weeks_in_slot(p, position) > 0 else "BENCH"
        elif position in _MULTI_SLOT_POSITIONS:
            ranked = sorted(group, key=lambda p: -_started_weeks_in_slot(p, position))
            starters = [p for p in ranked if _started_weeks_in_slot(p, position) > 0]
            benched = [p for p in ranked if _started_weeks_in_slot(p, position) == 0]
            for i, p in enumerate(starters[:2]):
                roles[p.player.espn_id] = f"{position}{i + 1}"
            for p in starters[2:] + benched:
                roles[p.player.espn_id] = "BENCH"
        # Any other/unknown position (e.g. blank position for never-rostered
        # picks) gets no role — _tier_line handles a missing role gracefully.

    return roles


def _tier_line(pick: DraftPick, role: str | None, positional_rankings: dict[str, list[PositionRanking]]) -> str:
    if role is None or role == "BENCH":
        return "role: BENCH (never started at this position) — no positional tier applies"

    real_position = pick.player.position
    if role == "FLEX":
        threshold = _FLEX_THRESHOLDS.get(real_position)
        role_label = f"FLEX ({real_position})"
    else:
        threshold = _TIER_THRESHOLDS.get(role)
        role_label = role

    entry = next((r for r in positional_rankings.get(real_position, []) if r.espn_id == pick.player.espn_id), None)
    if entry is None or threshold is None:
        return f"role: {role_label} — season-long positional finish unavailable"

    verdict = "CLEARED" if entry.rank <= threshold else "MISSED"
    return (
        f"role: {role_label} (needed top-{threshold} at {real_position} to matter) — finished the season "
        f"ranked #{entry.rank} at {real_position} ({entry.points:.1f} pts) → {verdict} the bar"
    )
