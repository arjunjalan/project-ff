from pydantic import BaseModel


class WeeklyPerformance(BaseModel):
    week: int
    points: float
    # Starting lineup slot that week (e.g. "WR", "RB/WR/TE", "BE", "IR").
    # "BE"/"IR" means benched/reserve that week, not absent from the roster.
    slot: str


class Player(BaseModel):
    espn_id: int
    name: str
    position: str
    pro_team: str | None = None
    # Season total. For players still on the *current* live roster this
    # comes straight from ESPN; for players who've since left (traded,
    # dropped, cut in a later season) it's summed from `weekly` instead —
    # see EspnAdapter. Prefer `weekly` for retrospective analysis: this
    # season total doesn't distinguish "played well every week" from
    # "played great for 8 weeks, then missed 6" — points-per-active-week
    # does.
    total_points: float = 0
    # Only populated for the requesting user's own team (see EspnAdapter) —
    # per-week points/slot for every week the player was on that roster,
    # even if they've since left it. Empty for every other team's players.
    weekly: list[WeeklyPerformance] = []


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


class LeagueSettings(BaseModel):
    team_count: int
    scoring_type: str
    points_per_reception: float
    playoff_team_count: int
    keeper_count: int
    # Non-zero starting-roster slots only, e.g. {"QB": 1, "RB": 2, "BE": 4}
    position_slot_counts: dict[str, int]


class League(BaseModel):
    espn_id: int
    year: int
    name: str
    teams: list[Team]
    draft: list[DraftPick] = []
    settings: LeagueSettings | None = None
