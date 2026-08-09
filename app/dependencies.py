from functools import lru_cache

from app.adapters.espn import EspnAdapter
from app.adapters.espn_rss import EspnRssAdapter
from app.adapters.llm import LLMAdapter
from app.adapters.open_router import OpenRouterAdapter
from app.config import settings
from app.services.league_service import LeagueService
from app.services.research_service import ResearchService
from app.services.retrospective_service import RetrospectiveService
from app.services.strategy_service import StrategyService
from app.storage.json_store import JsonStore
from app.storage.store import Store


@lru_cache
def get_store() -> Store:
    return JsonStore(settings.data_dir)


@lru_cache
def get_llm_adapter() -> LLMAdapter:
    return OpenRouterAdapter(
        api_key=settings.openrouter_api_key,
        model=settings.llm_model,
        fallback_model=settings.llm_fallback_model,
    )


@lru_cache
def get_league_service() -> LeagueService:
    adapter = EspnAdapter(
        league_id=settings.espn_league_id,
        espn_s2=settings.espn_s2,
        swid=settings.espn_swid,
    )
    return LeagueService(adapter, get_store())


@lru_cache
def get_research_service() -> ResearchService:
    return ResearchService(EspnRssAdapter(), get_llm_adapter())


@lru_cache
def get_retrospective_service() -> RetrospectiveService:
    return RetrospectiveService(get_store(), get_llm_adapter())


@lru_cache
def get_strategy_service() -> StrategyService:
    return StrategyService(
        get_store(),
        get_llm_adapter(),
        get_retrospective_service(),
        get_research_service(),
    )
