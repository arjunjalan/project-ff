from espn_api.football import League as EspnLeagueClient

from app.models.league import DraftPick, League, LeagueSettings, Player, Team


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
        # from current rosters (misses players since traded/dropped/retired).
        player_lookup = {p.espn_id: p for t in teams for p in t.roster}
        return League(
            espn_id=self._league_id,
            year=year,
            name=client.settings.name,
            teams=teams,
            draft=[_to_draft_pick(p, player_lookup) for p in client.draft],
            settings=_to_league_settings(client.settings),
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
