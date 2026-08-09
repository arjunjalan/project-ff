import json
import logging

from espn_api.football import League as EspnLeagueClient

from app.models.league import DraftPick, League, LeagueSettings, Player, PositionRanking, Team, WeeklyPerformance

logger = logging.getLogger(__name__)

# ESPN's internal lineup-slot IDs for each position we rank (from
# espn_api.football.constant.POSITION_MAP) — used to query the league-wide
# player pool by position via the same authenticated request client espn-api
# itself uses (not a scraped/undocumented path).
_POSITION_SLOT_IDS = {"QB": 0, "RB": 2, "WR": 4, "TE": 6, "D/ST": 16, "K": 17}


class EspnAdapter:
    def __init__(self, league_id: int, espn_s2: str, swid: str):
        self._league_id = league_id
        self._espn_s2 = espn_s2
        self._swid = swid

    def fetch_league(self, year: int) -> League:
        client = EspnLeagueClient(
            league_id=self._league_id,
            year=year,
            espn_s2=self._espn_s2,
            swid=self._swid,
        )
        teams = [_to_team(t, self._swid) for t in client.teams]
        # BasePick only carries playerId/playerName, not position — backfill
        # from current rosters (misses players since traded/dropped/retired
        # off the *current* roster; the weekly enrichment below fills most
        # of that gap for the requesting user's own team specifically).
        player_lookup = {p.espn_id: p for t in teams for p in t.roster}

        my_team = next((t for t in teams if t.is_mine), None)
        if my_team is not None:
            _enrich_with_weekly_performance(client, my_team.espn_id, player_lookup)

        return League(
            espn_id=self._league_id,
            year=year,
            name=client.settings.name,
            teams=teams,
            draft=[_to_draft_pick(p, player_lookup) for p in client.draft],
            settings=_to_league_settings(client.settings),
            positional_rankings=_fetch_positional_rankings(client, year),
        )


def _to_player(espn_player) -> Player:
    return Player(
        espn_id=espn_player.playerId,
        name=espn_player.name,
        position=espn_player.position,
        pro_team=getattr(espn_player, "proTeam", None),
        total_points=getattr(espn_player, "total_points", 0),
    )


def _to_team(espn_team, swid: str) -> Team:
    owner = espn_team.owners[0].get("displayName") if espn_team.owners else None
    is_mine = any(str(o.get("id", "")).upper() == swid.upper() for o in espn_team.owners)
    return Team(
        espn_id=espn_team.team_id,
        name=espn_team.team_name,
        owner=owner,
        is_mine=is_mine,
        division_name=espn_team.division_name or None,
        wins=espn_team.wins,
        losses=espn_team.losses,
        ties=espn_team.ties,
        points_for=espn_team.points_for,
        points_against=espn_team.points_against,
        final_standing=espn_team.final_standing or None,
        roster=[_to_player(p) for p in espn_team.roster],
    )


def _to_league_settings(espn_settings) -> LeagueSettings:
    ppr = next(
        (row["points"] for row in espn_settings.scoring_format if row.get("abbr") == "REC"),
        0.0,
    )
    slots = {k: v for k, v in espn_settings.position_slot_counts.items() if v and k}
    return LeagueSettings(
        team_count=espn_settings.team_count,
        scoring_type=espn_settings.scoring_type,
        points_per_reception=ppr,
        playoff_team_count=espn_settings.playoff_team_count,
        keeper_count=espn_settings.keeper_count,
        position_slot_counts=slots,
    )


def _fetch_positional_rankings(client, year: int) -> dict[str, list[PositionRanking]]:
    """Season-long positional finish, under this league's own scoring rules.

    Reuses espn_api's own authenticated request client (client.espn_request)
    with a broader filter than its built-in free_agents() — that method only
    returns *unrostered* players, which excludes most of the players anyone
    actually drafted. This queries the same underlying endpoint for the full
    rostered+free-agent pool at each position, sorted by season point total.
    """
    stat_id = f"00{year}"
    result: dict[str, list[PositionRanking]] = {}

    for position, slot_id in _POSITION_SLOT_IDS.items():
        try:
            params = {"view": "kona_player_info", "scoringPeriodId": client.finalScoringPeriod}
            filters = {
                "players": {
                    "filterSlotIds": {"value": [slot_id]},
                    "limit": 60,
                    "sortAppliedStatTotal": {"sortAsc": False, "sortPriority": 1, "value": stat_id},
                }
            }
            headers = {"x-fantasy-filter": json.dumps(filters)}
            data = client.espn_request.league_get(params=params, headers=headers)
        except Exception:
            logger.warning("Failed to fetch positional rankings for %s", position, exc_info=True)
            continue

        entries = []
        for row in data.get("players", []):
            info = row.get("player", {})
            total = next(
                (s.get("appliedTotal", 0.0) for s in info.get("stats", []) if s.get("id") == stat_id),
                0.0,
            )
            entries.append((info.get("id"), info.get("fullName", ""), total))

        entries.sort(key=lambda e: e[2], reverse=True)
        result[position] = [
            PositionRanking(espn_id=espn_id, name=name, points=points, rank=i + 1)
            for i, (espn_id, name, points) in enumerate(entries)
            if espn_id is not None
        ]

    return result


def _enrich_with_weekly_performance(client, my_team_espn_id: int, player_lookup: dict[int, Player]) -> None:
    """Fetch per-week lineup data for one team and attach it to `player_lookup`.

    Covers every player who spent any week on that team's roster during the
    season — including ones since traded/dropped, who the *current* roster
    snapshot (`player_lookup` as passed in) doesn't know about at all.
    """
    weekly_by_player: dict[int, list[WeeklyPerformance]] = {}
    player_info: dict[int, tuple[str, str, str | None]] = {}

    num_weeks = getattr(client.settings, "reg_season_count", 0) or 0
    for week in range(1, num_weeks + 1):
        try:
            matchups = client.box_scores(week)
        except Exception:
            logger.warning("Failed to fetch box scores for week %d", week, exc_info=True)
            continue

        for m in matchups:
            home_id = getattr(getattr(m, "home_team", None), "team_id", None)
            away_id = getattr(getattr(m, "away_team", None), "team_id", None)
            if home_id == my_team_espn_id:
                lineup = m.home_lineup
            elif away_id == my_team_espn_id:
                lineup = m.away_lineup
            else:
                continue

            for bp in lineup:
                weekly_by_player.setdefault(bp.playerId, []).append(
                    WeeklyPerformance(week=week, points=bp.points, slot=bp.slot_position)
                )
                player_info.setdefault(bp.playerId, (bp.name, bp.position, getattr(bp, "proTeam", None)))
            break

    for espn_id, weekly in weekly_by_player.items():
        weekly.sort(key=lambda w: w.week)
        if espn_id in player_lookup:
            player_lookup[espn_id].weekly = weekly
            # `total_points` from the live player object is whole-season NFL
            # output, not points earned specifically on this roster (they
            # can differ a lot for anyone traded/dropped mid-season on
            # *this* team but still active elsewhere). Weekly sum is what
            # this team actually earned.
            player_lookup[espn_id].total_points = sum(w.points for w in weekly)
        else:
            name, position, pro_team = player_info[espn_id]
            player_lookup[espn_id] = Player(
                espn_id=espn_id,
                name=name,
                position=position,
                pro_team=pro_team,
                total_points=sum(w.points for w in weekly),
                weekly=weekly,
            )


def _to_draft_pick(espn_pick, player_lookup: dict[int, Player]) -> DraftPick:
    player = player_lookup.get(espn_pick.playerId) or Player(
        espn_id=espn_pick.playerId,
        name=espn_pick.playerName,
        position="",
        pro_team=None,
    )
    return DraftPick(
        round_num=espn_pick.round_num,
        round_pick=espn_pick.round_pick,
        team_espn_id=espn_pick.team.team_id,
        team_name=espn_pick.team.team_name,
        player=player,
    )
