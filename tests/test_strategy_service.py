from app.adapters.llm import LLMAdapter, LLMResult
from app.models.league import League, LeagueSettings, Team
from app.models.news import MaterialityAssessment, NewsItem
from app.models.retrospective import TeamRetrospective
from app.services.strategy_service import StrategyService


class FakeStore:
    def __init__(self, leagues: dict[str, League]):
        self._leagues = leagues

    def save(self, key, model):
        raise AssertionError("strategy service should not write")

    def load(self, key, model_cls):
        return self._leagues.get(key)


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


def make_retro():
    return TeamRetrospective(
        team_name="Shiznits", year=2025, wins=8, losses=6, final_standing=5, picks=[], narrative="drafted RBs too early"
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
