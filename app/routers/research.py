from fastapi import APIRouter, Depends

from app.dependencies import get_research_service
from app.models.news import MaterialityAssessment
from app.services.research_service import ResearchService

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/feed", response_model=list[MaterialityAssessment])
def get_feed(limit: int = 25, service: ResearchService = Depends(get_research_service)):
    return service.get_materiality_feed(limit=limit)
