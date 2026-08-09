from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_league_service
from app.models.league import League
from app.services.league_service import LeagueService

router = APIRouter(prefix="/league", tags=["league"])


@router.get("/{year}", response_model=League)
def get_league(year: int, service: LeagueService = Depends(get_league_service)):
    league = service.get(year)
    if league is None:
        raise HTTPException(status_code=404, detail=f"No synced data for {year} — POST /league/{year}/sync first")
    return league


@router.post("/{year}/sync", response_model=League)
def sync_league(year: int, service: LeagueService = Depends(get_league_service)):
    return service.sync(year)
