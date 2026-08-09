import pytest

from app.adapters.llm import LLMAdapter, LLMResult
from app.models.league import DraftPick, League, LeagueSettings, Player, Team, WeeklyPerformance
from app.models.retrospective import TeamRetrospective
from app.services.retrospective_service import RetrospectiveService, _pick_line, _position_breakdown


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


def test_get_retrospective_second_call_hits_cache_not_llm():
    league = make_league()
    store = FakeStore({"league_2025": league})
    llm = FakeLLM()
    service = RetrospectiveService(store, llm)

    first = service.get_retrospective(2025)
    second = service.get_retrospective(2025)

    assert first == second
    assert llm.call_count == 1
