import pytest

from app.adapters.llm import LLMAdapter, LLMResult
from app.models.league import DraftPick, League, Player, Team
from app.models.retrospective import TeamRetrospective
from app.services.retrospective_service import RetrospectiveService


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


def make_league():
    my_team = Team(espn_id=1, name="My Team", is_mine=True, wins=8, losses=6, final_standing=5)
    other_team = Team(espn_id=2, name="Other Team", is_mine=False, wins=7, losses=7, final_standing=6)
    draft = [
        DraftPick(
            round_num=1,
            round_pick=1,
            team_espn_id=1,
            team_name="My Team",
            player=Player(espn_id=10, name="Star Bust", position="RB", total_points=50),
        ),
        DraftPick(
            round_num=10,
            round_pick=5,
            team_espn_id=1,
            team_name="My Team",
            player=Player(espn_id=11, name="Late Steal", position="WR", total_points=200),
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
    assert [p.player.name for p in result.picks] == ["Star Bust", "Late Steal"]
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


def test_narrative_prompt_includes_picks_and_points():
    league = make_league()
    llm = FakeLLM()
    service = RetrospectiveService(FakeStore({"league_2025": league}), llm)

    service.get_retrospective(2025)

    user_content = llm.last_messages[1]["content"]
    assert "Star Bust" in user_content
    assert "Late Steal" in user_content
    assert "200" in user_content


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


def test_get_retrospective_second_call_hits_cache_not_llm():
    league = make_league()
    store = FakeStore({"league_2025": league})
    llm = FakeLLM()
    service = RetrospectiveService(store, llm)

    first = service.get_retrospective(2025)
    second = service.get_retrospective(2025)

    assert first == second
    assert llm.call_count == 1
