from pydantic import BaseModel

from app.models.league import DraftPick


class TeamRetrospective(BaseModel):
    team_name: str
    year: int
    wins: int
    losses: int
    final_standing: int | None
    picks: list[DraftPick]
    narrative: str
    # Raw per-position aggregates (points + rate), same data the retrospective's
    # own LLM call used — passed through as-is to StrategyService so it isn't
    # working from a lossy re-summary of a summary.
    position_breakdown: list[str] = []
