from pydantic import BaseModel


class StrategyBrief(BaseModel):
    year: int
    league_settings_summary: str
    narrative: str
    draft_slot: int | None = None
