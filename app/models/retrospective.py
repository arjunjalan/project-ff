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
    # Season waiver/free-agent activity for this team (executed adds/drops,
    # FAAB spent, standout pickups) — see EspnAdapter._fetch_transactions.
    # Empty for years synced before transaction capture landed.
    transaction_summary: list[str] = []
