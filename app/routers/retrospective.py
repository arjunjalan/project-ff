from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_retrospective_service
from app.models.retrospective import TeamRetrospective
from app.services.retrospective_service import RetrospectiveService

router = APIRouter(prefix="/retrospective", tags=["retrospective"])


@router.get("/{year}", response_model=TeamRetrospective)
def get_retrospective(year: int, service: RetrospectiveService = Depends(get_retrospective_service)):
    try:
        retrospective = service.get_retrospective(year)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if retrospective is None:
        raise HTTPException(status_code=404, detail=f"No synced data for {year} — POST /league/{year}/sync first")
    return retrospective
