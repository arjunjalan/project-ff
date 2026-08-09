"""Spike: confirm ESPN's unofficial API retains historical (2025) league data.

Not part of the app — throwaway script per start_prompt.md's open risk.
Run: uv run python scripts/spike_historical_data.py
"""

import os

from dotenv import load_dotenv
from espn_api.football import League

load_dotenv()

LEAGUE_ID = int(os.environ["ESPN_LEAGUE_ID"])
ESPN_S2 = os.environ["ESPN_S2"]
SWID = os.environ["ESPN_SWID"]


def try_season(year: int) -> None:
    print(f"\n=== Season {year} ===")
    try:
        league = League(league_id=LEAGUE_ID, year=year, espn_s2=ESPN_S2, swid=SWID)
    except Exception as e:
        print(f"FAILED to load league: {e!r}")
        return

    print(f"League loaded: {league.settings.name}")

    try:
        teams = league.teams
        print(f"Teams: {len(teams)} — e.g. {teams[0].team_name if teams else 'none'}")
    except Exception as e:
        print(f"Teams FAILED: {e!r}")

    try:
        draft = league.draft
        print(f"Draft picks: {len(draft)}" + (f" — pick 1: {draft[0]}" if draft else " (empty)"))
    except Exception as e:
        print(f"Draft FAILED: {e!r}")

    try:
        standings = league.standings()
        print(f"Standings: {[t.team_name for t in standings]}")
    except Exception as e:
        print(f"Standings FAILED: {e!r}")

    try:
        activity = league.recent_activity(size=25)
        print(f"Recent activity items: {len(activity)}")
    except Exception as e:
        print(f"Recent activity (transactions) FAILED: {e!r}")


if __name__ == "__main__":
    try_season(2026)
    try_season(2025)
