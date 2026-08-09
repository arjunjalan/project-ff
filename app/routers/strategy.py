from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_strategy_service
from app.models.strategy import StrategyBrief
from app.services.strategy_service import StrategyService

router = APIRouter(prefix="/strategy", tags=["strategy"])


@router.get("/{year}", response_model=StrategyBrief)
def get_strategy(year: int, service: StrategyService = Depends(get_strategy_service)):
    brief = service.get_strategy(year)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"No synced data for {year} — POST /league/{year}/sync first")
    return brief
