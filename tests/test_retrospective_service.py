import pytest

from app.adapters.llm import LLMAdapter, LLMResult
from app.models.league import (
    DraftPick,
    League,
    LeagueSettings,
    Player,
    PositionRanking,
    Team,
    Transaction,
    TransactionItem,
    WeeklyPerformance,
)
from app.models.retrospective import TeamRetrospective
from app.services.retrospective_service import (
    RetrospectiveService,
    _assign_roles,
    _pick_line,
    _position_breakdown,
    _tier_line,
    _transaction_summary,
)


class FakeStore:
    def __init__(self, data: dict[str, object] | None = None):
        self._data = dict(data or {})

    def save(self, key, model):
        self._data[key] = model

    def load(self, key, model_cls):
        return self._data.get(key)


class FakeLLM(LLMAdapter):
    def __init__(self, text="a narrative"):
        self._text = text
        self.last_messages = None
        self.call_count = 0

    def chat(self, messages):
        self.call_count += 1
        self.last_messages = messages
        return LLMResult(text=self._text)


class ExplodingLLM(LLMAdapter):
    def chat(self, messages):
        raise AssertionError("LLM should not be called when a cached retrospective exists")


def weekly(count, points_each, slot="RB"):
    return [WeeklyPerformance(week=i + 1, points=points_each, slot=slot) for i in range(count)]


def make_league():
    my_team = Team(espn_id=1, name="My Team", is_mine=True, wins=8, losses=6, final_standing=5)
    other_team = Team(espn_id=2, name="Other Team", is_mine=False, wins=7, losses=7, final_standing=6)
    draft = [
        DraftPick(
            round_num=1,
            round_pick=1,
            team_espn_id=1,
            team_name="My Team",
            player=Player(
                espn_id=10, name="Star Bust", position="RB", total_points=50, weekly=weekly(10, 5.0)
            ),
        ),
        DraftPick(
            round_num=10,
            round_pick=5,
            team_espn_id=1,
            team_name="My Team",
            player=Player(
                espn_id=11, name="Late Steal", position="WR", total_points=200, weekly=weekly(10, 20.0, slot="WR")
            ),
        ),
        DraftPick(
            round_num=3,
            round_pick=1,
            team_espn_id=1,
            team_name="My Team",
            player=Player(espn_id=13, name="Never Started", position="", total_points=0, weekly=[]),
        ),
        DraftPick(
            round_num=2,
            round_pick=1,
            team_espn_id=2,
            team_name="Other Team",
            player=Player(espn_id=12, name="Not Mine", position="QB", total_points=300),
        ),
    ]
    return League(espn_id=1, year=2025, name="Test League", teams=[my_team, other_team], draft=draft)


def test_get_retrospective_filters_to_my_picks_and_sorts_by_round():
    league = make_league()
    llm = FakeLLM()
    service = RetrospectiveService(FakeStore({"league_2025": league}), llm)

    result = service.get_retrospective(2025)

    assert result.team_name == "My Team"
    assert result.wins == 8
    assert [p.player.name for p in result.picks] == ["Star Bust", "Never Started", "Late Steal"]
    assert result.narrative == "a narrative"


def test_get_retrospective_returns_none_when_no_synced_data():
    service = RetrospectiveService(FakeStore(), FakeLLM())
    assert service.get_retrospective(2025) is None


def test_get_retrospective_raises_when_no_team_is_mine():
    league = make_league()
    league.teams[0].is_mine = False
    service = RetrospectiveService(FakeStore({"league_2025": league}), FakeLLM())

    with pytest.raises(ValueError):
        service.get_retrospective(2025)


def test_narrative_prompt_includes_rate_and_weeks_started():
    league = make_league()
    llm = FakeLLM()
    service = RetrospectiveService(FakeStore({"league_2025": league}), llm)

    service.get_retrospective(2025)

    user_content = llm.last_messages[1]["content"]
    assert "Star Bust" in user_content
    assert "5.0 pts/week" in user_content
    assert "Late Steal" in user_content
    assert "20.0 pts/week" in user_content
    assert "Never Started" in user_content
    assert "production on this roster is unknown" in user_content


def test_narrative_prompt_includes_scoring_settings_when_available():
    league = make_league()
    league.settings = LeagueSettings(
        team_count=10,
        scoring_type="H2H_POINTS",
        points_per_reception=0.0,
        playoff_team_count=6,
        keeper_count=0,
        position_slot_counts={"QB": 1, "RB": 2, "WR": 2, "BE": 4},
    )
    llm = FakeLLM()
    service = RetrospectiveService(FakeStore({"league_2025": league}), llm)

    service.get_retrospective(2025)

    user_content = llm.last_messages[1]["content"]
    assert "Scoring rules that season" in user_content
    assert "0.0 pt/reception" in user_content


def test_narrative_prompt_omits_scoring_line_when_settings_missing():
    league = make_league()
    assert league.settings is None
    llm = FakeLLM()
    service = RetrospectiveService(FakeStore({"league_2025": league}), llm)

    service.get_retrospective(2025)

    user_content = llm.last_messages[1]["content"]
    assert "Scoring rules that season" not in user_content


def test_pick_line_with_weekly_data_shows_rate_and_weeks_started():
    pick = DraftPick(
        round_num=1,
        round_pick=1,
        team_espn_id=1,
        team_name="My Team",
        player=Player(espn_id=1, name="X", position="RB", total_points=100, weekly=weekly(10, 10.0)),
    )
    line = _pick_line(pick)
    assert "on roster 10 of the season's weeks" in line
    assert "started 10 of them" in line
    assert "10.0 pts/week" in line


def test_pick_line_excludes_benched_weeks_from_started_count():
    started = weekly(5, 10.0, slot="RB")
    benched = weekly(3, 0.0, slot="BE")
    pick = DraftPick(
        round_num=1,
        round_pick=1,
        team_espn_id=1,
        team_name="My Team",
        player=Player(espn_id=1, name="X", position="RB", total_points=50, weekly=started + benched),
    )
    line = _pick_line(pick)
    assert "on roster 8 of the season's weeks" in line
    assert "started 5 of them" in line


def test_pick_line_never_on_roster():
    pick = DraftPick(
        round_num=1,
        round_pick=1,
        team_espn_id=1,
        team_name="My Team",
        player=Player(espn_id=1, name="X", position="", total_points=0, weekly=[]),
    )
    line = _pick_line(pick)
    assert "never appeared in a weekly lineup" in line
    assert "production on this roster is unknown" in line


def test_get_retrospective_caches_result_after_first_computation():
    league = make_league()
    store = FakeStore({"league_2025": league})
    llm = FakeLLM()
    service = RetrospectiveService(store, llm)

    service.get_retrospective(2025)

    cached = store.load("retrospective_2025", TeamRetrospective)
    assert cached is not None
    assert cached.team_name == "My Team"
    assert llm.call_count == 1


def test_get_retrospective_uses_cache_and_never_calls_llm():
    cached = TeamRetrospective(
        team_name="My Team", year=2025, wins=8, losses=6, final_standing=5, picks=[], narrative="cached narrative"
    )
    store = FakeStore({"retrospective_2025": cached})
    service = RetrospectiveService(store, ExplodingLLM())

    result = service.get_retrospective(2025)

    assert result.narrative == "cached narrative"


def test_narrative_prompt_tags_picks_as_early_or_late_round():
    league = make_league()
    llm = FakeLLM()
    service = RetrospectiveService(FakeStore({"league_2025": league}), llm)

    service.get_retrospective(2025)

    user_content = llm.last_messages[1]["content"]
    # my picks are rounds 1, 3, 10 -> max_round=10, midpoint=5.0
    assert "Round 1, Pick 1 (early-round)" in user_content
    assert "Round 3, Pick 1 (early-round)" in user_content
    assert "Round 10, Pick 5 (late-round)" in user_content


def test_narrative_prompt_includes_position_breakdown_section():
    league = make_league()
    llm = FakeLLM()
    service = RetrospectiveService(FakeStore({"league_2025": league}), llm)

    service.get_retrospective(2025)

    user_content = llm.last_messages[1]["content"]
    assert "Position breakdown" in user_content
    assert "RB: 1 pick(s), 50.0 pts total" in user_content
    assert "WR: 1 pick(s), 200.0 pts total" in user_content
    assert "Unknown: 1 pick(s)" in user_content


def test_position_breakdown_aggregates_multiple_picks_at_same_position():
    picks = [
        DraftPick(
            round_num=1,
            round_pick=1,
            team_espn_id=1,
            team_name="T",
            player=Player(espn_id=1, name="RB1", position="RB", total_points=100, weekly=weekly(10, 10.0)),
        ),
        DraftPick(
            round_num=5,
            round_pick=1,
            team_espn_id=1,
            team_name="T",
            player=Player(espn_id=2, name="RB2", position="RB", total_points=50, weekly=weekly(5, 10.0)),
        ),
    ]
    lines = _position_breakdown(picks)
    assert len(lines) == 1
    assert "RB: 2 pick(s), 150.0 pts total, 15 started-weeks, ~10.0 pts/started-week" in lines[0]


def test_position_breakdown_handles_zero_started_weeks_without_division_error():
    picks = [
        DraftPick(
            round_num=1,
            round_pick=1,
            team_espn_id=1,
            team_name="T",
            player=Player(espn_id=1, name="Ghost", position="WR", total_points=0, weekly=[]),
        ),
    ]
    lines = _position_breakdown(picks)
    assert "WR: 1 pick(s), 0.0 pts total, 0 started-weeks, ~0.0 pts/started-week" in lines[0]


def txn(team_espn_id=1, type_="WAIVER", status="EXECUTED", bid_amount=0, items=None):
    return Transaction(
        type=type_,
        status=status,
        team_espn_id=team_espn_id,
        team_name="My Team",
        scoring_period=1,
        date_epoch_ms=1000,
        bid_amount=bid_amount,
        items=items or [],
    )


def test_transaction_summary_counts_executed_adds_drops_and_faab():
    my_team = Team(espn_id=1, name="My Team", is_mine=True, wins=8, losses=6)
    transactions = [
        txn(
            bid_amount=15,
            items=[
                TransactionItem(action="ADD", player=Player(espn_id=1, name="Add1", position="RB")),
                TransactionItem(action="DROP", player=Player(espn_id=2, name="Drop1", position="WR")),
            ],
        ),
        txn(type_="FREEAGENT", items=[TransactionItem(action="ADD", player=Player(espn_id=3, name="Add2", position="TE"))]),
        txn(status="FAILED_ROSTERLOCK", bid_amount=99, items=[]),  # excluded — not executed
        txn(team_espn_id=2, bid_amount=50, items=[]),  # excluded — other team
    ]
    lines = _transaction_summary(my_team, transactions)
    assert "2 executed moves this season: 2 unique players added, 1 drops, $15 FAAB spent" in lines[0]


def test_transaction_summary_empty_when_no_executed_transactions():
    my_team = Team(espn_id=1, name="My Team", is_mine=True, wins=8, losses=6)
    lines = _transaction_summary(my_team, [txn(status="FAILED_ROSTERLOCK")])
    assert lines == []


def test_transaction_summary_lists_notable_pickups_by_points_desc():
    my_team = Team(espn_id=1, name="My Team", is_mine=True, wins=8, losses=6)
    transactions = [
        txn(
            items=[
                TransactionItem(
                    action="ADD",
                    player=Player(espn_id=1, name="Low Add", position="RB", total_points=10, weekly=weekly(5, 2.0)),
                )
            ]
        ),
        txn(
            items=[
                TransactionItem(
                    action="ADD",
                    player=Player(espn_id=2, name="High Add", position="WR", total_points=80, weekly=weekly(8, 10.0)),
                )
            ]
        ),
        txn(items=[TransactionItem(action="ADD", player=Player(espn_id=3, name="Never Started", position="TE"))]),
    ]
    lines = _transaction_summary(my_team, transactions)
    pickup_lines = [l for l in lines if l.startswith("Notable pickup")]
    assert len(pickup_lines) == 2  # "Never Started" excluded — no weekly data
    assert pickup_lines[0].startswith("Notable pickup: High Add")
    assert pickup_lines[1].startswith("Notable pickup: Low Add")


def test_transaction_summary_dedupes_a_player_added_more_than_once():
    my_team = Team(espn_id=1, name="My Team", is_mine=True, wins=8, losses=6)
    player = Player(espn_id=1, name="Re-added Guy", position="RB", weekly=weekly(3, 10.0))
    transactions = [
        txn(items=[TransactionItem(action="ADD", player=player)]),
        txn(items=[TransactionItem(action="ADD", player=player)]),
    ]
    lines = _transaction_summary(my_team, transactions)
    assert "1 unique players added" in lines[0]
    assert len([l for l in lines if l.startswith("Notable pickup")]) == 1


def test_transaction_summary_flags_bench_stash_separately_from_notable():
    my_team = Team(espn_id=1, name="My Team", is_mine=True, wins=8, losses=6)
    # Mostly benched (7 weeks) at a high rate, started only 2 weeks — the
    # Drake Maye case: a good pickup that was barely played, not accurately
    # described by a raw season total next to a "started weeks" count. This
    # is reported as a fact ("Bench stash"), not judged as a mistake — see
    # Arjun's pushback on the original "Underused pickup" framing.
    mostly_benched = weekly(2, 20.0, slot="QB") + weekly(7, 18.0, slot="BE")
    player = Player(espn_id=1, name="Bench Riser", position="QB", weekly=mostly_benched)
    lines = _transaction_summary(my_team, [txn(items=[TransactionItem(action="ADD", player=player)])])

    notable = [l for l in lines if l.startswith("Notable pickup")]
    stashed = [l for l in lines if l.startswith("Bench stash")]
    assert len(notable) == 1  # started_points (40.0) > 0, still listed
    assert len(stashed) == 1
    assert "Bench Riser" in stashed[0]
    assert "started only 2 of 9 weeks" in stashed[0]
    assert "18.0 pts/week while benched" in stashed[0]
    assert "mistake" not in stashed[0] and "miss" not in stashed[0]


def test_transaction_summary_does_not_flag_bench_stash_when_bench_rate_is_low():
    my_team = Team(espn_id=1, name="My Team", is_mine=True, wins=8, losses=6)
    # Mostly benched, but low-production bench weeks — not a real signal.
    low_bench = weekly(1, 10.0, slot="RB") + weekly(5, 2.0, slot="BE")
    player = Player(espn_id=1, name="Scrub", position="RB", weekly=low_bench)
    lines = _transaction_summary(my_team, [txn(items=[TransactionItem(action="ADD", player=player)])])

    assert not [l for l in lines if l.startswith("Bench stash")]


def test_narrative_prompt_includes_transaction_summary_when_present():
    league = make_league()
    league.transactions = [
        txn(
            bid_amount=20,
            items=[TransactionItem(action="ADD", player=Player(espn_id=99, name="Waiver Pickup", position="RB"))],
        )
    ]
    llm = FakeLLM()
    service = RetrospectiveService(FakeStore({"league_2025": league}), llm)

    service.get_retrospective(2025)

    user_content = llm.last_messages[1]["content"]
    assert "Season waiver-wire activity" in user_content
    assert "1 executed moves this season: 1 unique players added" in user_content


def test_narrative_prompt_omits_transaction_section_when_no_transactions():
    league = make_league()
    assert league.transactions == []
    llm = FakeLLM()
    service = RetrospectiveService(FakeStore({"league_2025": league}), llm)

    service.get_retrospective(2025)

    user_content = llm.last_messages[1]["content"]
    assert "Season waiver-wire activity" not in user_content


def draft_pick(espn_id, position, weekly_data=None, total_points=0, round_num=1, round_pick=1):
    return DraftPick(
        round_num=round_num,
        round_pick=round_pick,
        team_espn_id=1,
        team_name="My Team",
        player=Player(
            espn_id=espn_id, name=f"P{espn_id}", position=position, total_points=total_points, weekly=weekly_data or []
        ),
    )


def test_assign_roles_ranks_two_rbs_by_weeks_started_in_dedicated_slot():
    rb1 = draft_pick(1, "RB", weekly(10, 10.0, slot="RB"))
    rb2 = draft_pick(2, "RB", weekly(5, 8.0, slot="RB"))
    roles = _assign_roles([rb1, rb2])
    assert roles[1] == "RB1"
    assert roles[2] == "RB2"


def test_assign_roles_assigns_flex_to_player_with_most_flex_weeks():
    rb_dedicated = draft_pick(1, "RB", weekly(10, 10.0, slot="RB"))
    rb_flex = draft_pick(2, "RB", weekly(8, 9.0, slot="RB/WR/TE"))
    roles = _assign_roles([rb_dedicated, rb_flex])
    assert roles[2] == "FLEX"
    assert roles[1] == "RB1"


def test_assign_roles_marks_never_started_as_bench():
    p = draft_pick(1, "QB", weekly(10, 5.0, slot="BE"))
    roles = _assign_roles([p])
    assert roles[1] == "BENCH"


def test_assign_roles_single_slot_position_gets_direct_label():
    p = draft_pick(1, "QB", weekly(10, 20.0, slot="QB"))
    roles = _assign_roles([p])
    assert roles[1] == "QB"


def test_assign_roles_third_rb_becomes_bench():
    rb1 = draft_pick(1, "RB", weekly(10, 10.0, slot="RB"))
    rb2 = draft_pick(2, "RB", weekly(10, 9.0, slot="RB"))
    rb3 = draft_pick(3, "RB", weekly(10, 8.0, slot="RB"))
    roles = _assign_roles([rb1, rb2, rb3])
    assert roles[1] == "RB1"
    assert roles[2] == "RB2"
    assert roles[3] == "BENCH"


def test_tier_line_cleared_bar():
    pick = draft_pick(1, "QB", total_points=300)
    rankings = {"QB": [PositionRanking(espn_id=1, name="P1", points=300, rank=2)]}
    line = _tier_line(pick, "QB", rankings)
    assert "CLEARED" in line
    assert "#2" in line


def test_tier_line_missed_bar():
    pick = draft_pick(1, "WR", total_points=100)
    rankings = {"WR": [PositionRanking(espn_id=1, name="P1", points=100, rank=20)]}
    line = _tier_line(pick, "WR1", rankings)
    assert "MISSED" in line
    assert "top-5" in line


def test_tier_line_flex_uses_flex_threshold_by_real_position():
    pick = draft_pick(1, "TE", total_points=100)
    rankings = {"TE": [PositionRanking(espn_id=1, name="P1", points=100, rank=9)]}
    line = _tier_line(pick, "FLEX", rankings)
    assert "CLEARED" in line
    assert "top-10" in line


def test_tier_line_bench_role_has_no_tier():
    pick = draft_pick(1, "RB")
    line = _tier_line(pick, "BENCH", {})
    assert "no positional tier applies" in line


def test_tier_line_none_role_has_no_tier():
    pick = draft_pick(1, "RB")
    line = _tier_line(pick, None, {})
    assert "no positional tier applies" in line


def test_tier_line_missing_ranking_data_is_graceful():
    pick = draft_pick(1, "RB")
    line = _tier_line(pick, "RB1", {})
    assert "unavailable" in line


def test_narrative_prompt_includes_tier_verdicts_when_rankings_available():
    league = make_league()
    league.positional_rankings = {
        "RB": [PositionRanking(espn_id=10, name="Star Bust", points=50, rank=40)],
        "WR": [PositionRanking(espn_id=11, name="Late Steal", points=200, rank=3)],
    }
    llm = FakeLLM()
    service = RetrospectiveService(FakeStore({"league_2025": league}), llm)

    service.get_retrospective(2025)

    user_content = llm.last_messages[1]["content"]
    assert "CLEARED" in user_content or "MISSED" in user_content
    assert "role:" in user_content


def test_get_retrospective_second_call_hits_cache_not_llm():
    league = make_league()
    store = FakeStore({"league_2025": league})
    llm = FakeLLM()
    service = RetrospectiveService(store, llm)

    first = service.get_retrospective(2025)
    second = service.get_retrospective(2025)

    assert first == second
    assert llm.call_count == 1
