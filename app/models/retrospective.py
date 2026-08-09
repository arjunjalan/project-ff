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
