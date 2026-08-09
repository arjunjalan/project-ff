from app.adapters.llm import LLMAdapter, LLMResult
from app.models.league import League, LeagueSettings, Team
from app.models.news import MaterialityAssessment, NewsItem
from app.models.retrospective import TeamRetrospective
from app.services.strategy_service import StrategyService, _snake_picks


class FakeStore:
    def __init__(self, data: dict[str, object] | None = None):
        self._data = dict(data or {})

    def save(self, key, model):
        self._data[key] = model

    def load(self, key, model_cls):
        return self._data.get(key)


class FakeLLM(LLMAdapter):
    def __init__(self, text="a strategy narrative"):
        self._text = text
        self.last_messages = None

    def chat(self, messages):
        self.last_messages = messages
        return LLMResult(text=self._text)


class FakeRetrospectiveService:
    def __init__(self, retro=None, raises=False):
        self._retro = retro
        self._raises = raises

    def get_retrospective(self, year):
        if self._raises:
            raise ValueError("no team found")
        return self._retro


class FakeResearchService:
    def __init__(self, assessments=None):
        self._assessments = assessments or []

    def get_materiality_feed(self, limit=25):
        return self._assessments


def make_league_with_settings():
    settings = LeagueSettings(
        team_count=12,
        scoring_type="H2H_POINTS",
        points_per_reception=1.0,
        playoff_team_count=6,
        keeper_count=0,
        position_slot_counts={"QB": 1, "RB": 2, "WR": 2, "BE": 4},
    )
    return League(espn_id=1, year=2026, name="Test League", teams=[], draft=[], settings=settings)


def make_retro(position_breakdown=None):
    return TeamRetrospective(
        team_name="Shiznits",
        year=2025,
        wins=8,
        losses=6,
        final_standing=5,
        picks=[],
        narrative="drafted RBs too early",
        position_breakdown=position_breakdown or [],
    )


def make_news_item(material=True):
    item = NewsItem(title="Star RB traded", summary="...", link="https://example.com")
    return MaterialityAssessment(item=item, material=material, reason="role change")


def test_get_strategy_returns_none_when_no_synced_league():
    service = StrategyService(FakeStore({}), FakeLLM(), FakeRetrospectiveService(), FakeResearchService())
    assert service.get_strategy(2026) is None


def test_get_strategy_returns_none_when_no_settings():
    league = League(espn_id=1, year=2026, name="Test League", teams=[], draft=[], settings=None)
    service = StrategyService(FakeStore({"league_2026": league}), FakeLLM(), FakeRetrospectiveService(), FakeResearchService())
    assert service.get_strategy(2026) is None


def test_get_strategy_includes_settings_retro_and_material_news_in_prompt():
    league = make_league_with_settings()
    llm = FakeLLM()
    retro_service = FakeRetrospectiveService(retro=make_retro())
    research_service = FakeResearchService([make_news_item(material=True), make_news_item(material=False)])
    service = StrategyService(FakeStore({"league_2026": league}), llm, retro_service, research_service)

    brief = service.get_strategy(2026)

    assert brief.year == 2026
    assert "12-team" in brief.league_settings_summary
    assert "1.0 pt/reception" in brief.league_settings_summary
    user_content = llm.last_messages[1]["content"]
    assert "drafted RBs too early" in user_content
    assert "Star RB traded" in user_content
    assert brief.narrative == "a strategy narrative"


def test_get_strategy_includes_raw_position_breakdown_when_available():
    league = make_league_with_settings()
    llm = FakeLLM()
    retro = make_retro(position_breakdown=["RB: 4 pick(s), 350.0 pts total, 30 started-weeks, ~11.6 pts/started-week"])
    retro_service = FakeRetrospectiveService(retro=retro)
    service = StrategyService(FakeStore({"league_2026": league}), llm, retro_service, FakeResearchService())

    service.get_strategy(2026)

    user_content = llm.last_messages[1]["content"]
    assert "position-by-position breakdown" in user_content
    assert "~11.6 pts/started-week" in user_content


def test_get_strategy_omits_position_breakdown_section_when_empty():
    league = make_league_with_settings()
    llm = FakeLLM()
    retro_service = FakeRetrospectiveService(retro=make_retro(position_breakdown=[]))
    service = StrategyService(FakeStore({"league_2026": league}), llm, retro_service, FakeResearchService())

    service.get_strategy(2026)

    assert "position-by-position breakdown" not in llm.last_messages[1]["content"]


def test_get_strategy_handles_missing_retrospective_gracefully():
    league = make_league_with_settings()
    retro_service = FakeRetrospectiveService(raises=True)
    llm = FakeLLM()
    service = StrategyService(FakeStore({"league_2026": league}), llm, retro_service, FakeResearchService())

    brief = service.get_strategy(2026)

    assert brief is not None
    assert "No retrospective available" in llm.last_messages[1]["content"]


def test_get_strategy_handles_no_material_news():
    league = make_league_with_settings()
    research_service = FakeResearchService([make_news_item(material=False)])
    llm = FakeLLM()
    service = StrategyService(
        FakeStore({"league_2026": league}), llm, FakeRetrospectiveService(), research_service
    )

    service.get_strategy(2026)

    assert "No current material news available" in llm.last_messages[1]["content"]


def make_league(year, ppr, settings=True):
    league_settings = (
        LeagueSettings(
            team_count=12,
            scoring_type="H2H_POINTS",
            points_per_reception=ppr,
            playoff_team_count=6,
            keeper_count=0,
            position_slot_counts={"QB": 1, "RB": 2, "WR": 2, "BE": 4},
        )
        if settings
        else None
    )
    return League(espn_id=1, year=year, name="Test League", teams=[], draft=[], settings=league_settings)


def test_get_strategy_flags_scoring_format_change():
    league_2026 = make_league(2026, ppr=1.0)
    league_2025 = make_league(2025, ppr=0.0)
    llm = FakeLLM()
    service = StrategyService(
        FakeStore({"league_2026": league_2026, "league_2025": league_2025}),
        llm,
        FakeRetrospectiveService(retro=make_retro()),
        FakeResearchService(),
    )

    service.get_strategy(2026)

    user_content = llm.last_messages[1]["content"]
    assert "SCORING FORMAT CHANGE" in user_content
    assert "0.0" in user_content and "1.0" in user_content
    assert "2025" in user_content and "2026" in user_content


def test_get_strategy_no_scoring_change_note_when_ppr_unchanged():
    league_2026 = make_league(2026, ppr=1.0)
    league_2025 = make_league(2025, ppr=1.0)
    llm = FakeLLM()
    service = StrategyService(
        FakeStore({"league_2026": league_2026, "league_2025": league_2025}),
        llm,
        FakeRetrospectiveService(retro=make_retro()),
        FakeResearchService(),
    )

    service.get_strategy(2026)

    assert "SCORING FORMAT CHANGE" not in llm.last_messages[1]["content"]


def test_get_strategy_caches_brief_and_does_not_call_llm_again():
    league = make_league_with_settings()
    llm = FakeLLM()
    store = FakeStore({"league_2026": league})
    service = StrategyService(store, llm, FakeRetrospectiveService(retro=make_retro()), FakeResearchService())

    first = service.get_strategy(2026)
    second = service.get_strategy(2026)

    assert store.load("strategy_2026", None) is not None
    assert second == first
    # LLM should only have been asked once — the second call served from cache.
    assert llm.last_messages is not None
    llm.last_messages = None
    third = service.get_strategy(2026)
    assert llm.last_messages is None
    assert third == first


def test_snake_picks_computes_correct_pick_numbers_for_slot_8_of_12():
    settings = LeagueSettings(
        team_count=12,
        scoring_type="H2H_POINTS",
        points_per_reception=1.0,
        playoff_team_count=6,
        keeper_count=0,
        position_slot_counts={"QB": 1, "RB": 2, "WR": 2, "BE": 4},
    )

    assert _snake_picks(8, settings) == [8, 17, 32, 41, 56, 65, 80, 89, 104]


def test_get_strategy_includes_recorded_draft_slot_in_brief_and_prompt():
    league = make_league_with_settings()
    llm = FakeLLM()
    service = StrategyService(
        FakeStore({"league_2026": league}), llm, FakeRetrospectiveService(retro=make_retro()), FakeResearchService()
    )

    brief = service.get_strategy(2026)

    assert brief.draft_slot == 8
    user_content = llm.last_messages[1]["content"]
    assert "draft slot: 8" in user_content
    assert "8, 17, 32" in user_content


def test_get_strategy_omits_draft_slot_for_year_without_a_recorded_slot():
    league = make_league(2027, ppr=1.0)
    llm = FakeLLM()
    service = StrategyService(
        FakeStore({"league_2027": league}), llm, FakeRetrospectiveService(retro=make_retro()), FakeResearchService()
    )

    brief = service.get_strategy(2027)

    assert brief.draft_slot is None
    assert "No draft slot recorded" in llm.last_messages[1]["content"]


def test_get_strategy_no_scoring_change_note_when_prior_league_missing():
    league_2026 = make_league(2026, ppr=1.0)
    llm = FakeLLM()
    service = StrategyService(
        FakeStore({"league_2026": league_2026}), llm, FakeRetrospectiveService(retro=make_retro()), FakeResearchService()
    )

    service.get_strategy(2026)

    assert "SCORING FORMAT CHANGE" not in llm.last_messages[1]["content"]
