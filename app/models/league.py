from pydantic import BaseModel


class Player(BaseModel):
    espn_id: int
    name: str
    position: str
    pro_team: str | None = None
    # 0 for a drafted player traded/dropped off the roster before season end
    # (backfilled from final rosters — see EspnAdapter), not necessarily 0
    # points actually scored. Don't read this as "this pick was a bust."
    total_points: float = 0


class DraftPick(BaseModel):
    round_num: int
    round_pick: int
    team_espn_id: int
    team_name: str
    player: Player


class Team(BaseModel):
    espn_id: int
    name: str
    owner: str | None = None
    is_mine: bool = False
    division_name: str | None = None
    wins: int
    losses: int
    ties: int = 0
    points_for: float = 0
    points_against: float = 0
    final_standing: int | None = None
    roster: list[Player] = []


class Transaction(BaseModel):
    # Placeholder for H5 — the historical feed this shape was modeled on
    # isn't reliably queryable (see scripts/spike_historical_data.py);
    # unverified against the current-season feed.
    type: str
    team_espn_id: int
    player: Player | None = None


class League(BaseModel):
    espn_id: int
    year: int
    name: str
    teams: list[Team]
    draft: list[DraftPick] = []
