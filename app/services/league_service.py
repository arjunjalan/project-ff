from app.adapters.espn import EspnAdapter
from app.models.league import League
from app.storage.json_store import JsonStore


class LeagueService:
    def __init__(self, adapter: EspnAdapter, store: JsonStore):
        self._adapter = adapter
        self._store = store

    def sync(self, year: int) -> League:
        league = self._adapter.fetch_league(year)
        self._store.save(f"league_{year}", league)
        return league

    def get(self, year: int) -> League | None:
        return self._store.load(f"league_{year}", League)
