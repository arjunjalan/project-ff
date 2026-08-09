from app.models.league import LeagueSettings


def summarize_settings(s: LeagueSettings) -> str:
    starters = {k: v for k, v in s.position_slot_counts.items() if k not in ("BE", "IR")}
    starters_str = ", ".join(f"{v} {k}" for k, v in starters.items())
    return (
        f"{s.team_count}-team {s.scoring_type}, {s.points_per_reception} pt/reception, "
        f"starters: {starters_str}, playoff teams: {s.playoff_team_count}, keepers: {s.keeper_count}"
    )
