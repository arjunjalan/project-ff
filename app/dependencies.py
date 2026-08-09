from functools import lru_cache

from app.adapters.espn import EspnAdapter
from app.adapters.espn_rss import EspnRssAdapter
from app.adapters.open_router import OpenRouterAdapter
from app.config import settings
from app.services.league_service import LeagueService
from app.services.research_service import ResearchService
from app.storage.json_store import JsonStore


@lru_cache
def get_league_service() -> LeagueService:
    adapter = EspnAdapter(
        league_id=settings.espn_league_id,
        espn_s2=settings.espn_s2,
        swid=settings.espn_swid,
    )
    store = JsonStore(settings.data_dir)
    return LeagueService(adapter, store)


@lru_cache
def get_research_service() -> ResearchService:
    llm = OpenRouterAdapter(
        api_key=settings.openrouter_api_key,
        model=settings.llm_model,
        fallback_model=settings.llm_fallback_model,
    )
    return ResearchService(EspnRssAdapter(), llm)
