from functools import lru_cache

from app.adapters.espn import EspnAdapter
from app.config import settings
from app.services.league_service import LeagueService
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
