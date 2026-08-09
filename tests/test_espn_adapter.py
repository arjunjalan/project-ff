from types import SimpleNamespace

from app.adapters.espn import (
    _enrich_with_weekly_performance,
    _fetch_positional_rankings,
    _to_draft_pick,
    _to_league_settings,
    _to_player,
    _to_team,
)
from app.models.league import Player


def fake_player(espn_id=1, name="Bijan Robinson", position="RB", pro_team="ATL", total_points=0):
    return SimpleNamespace(
        playerId=espn_id, name=name, position=position, proTeam=pro_team, total_points=total_points
    )


def fake_team(espn_id=1, roster=None, owner_id="{OWNER-ID}"):
    return SimpleNamespace(
        team_id=espn_id,
        team_name="Giovanni's Grand Team",
        owners=[{"displayName": "giovanni", "id": owner_id}],
        division_name="League Standings",
        wins=10,
        losses=4,
        ties=0,
        points_for=1500.5,
        points_against=1200.25,
        final_standing=2,
        roster=roster or [fake_player()],
    )


def test_to_player_maps_fields():
    player = _to_player(fake_player(total_points=123.4))
    assert player.espn_id == 1
    assert player.name == "Bijan Robinson"
    assert player.position == "RB"
    assert player.pro_team == "ATL"
    assert player.total_points == 123.4


def test_to_team_maps_owner_and_roster():
    team = _to_team(fake_team(), swid="{OWNER-ID}")
    assert team.owner == "giovanni"
    assert team.final_standing == 2
    assert len(team.roster) == 1
    assert team.roster[0].name == "Bijan Robinson"
    assert team.is_mine is True


def test_to_team_is_mine_false_when_swid_does_not_match():
    team = _to_team(fake_team(), swid="{SOMEONE-ELSE}")
    assert team.is_mine is False


def test_to_team_handles_no_owners():
    espn_team = fake_team()
    espn_team.owners = []
    team = _to_team(espn_team, swid="{OWNER-ID}")
    assert team.owner is None
    assert team.is_mine is False


def test_to_draft_pick_backfills_position_from_roster():
    drafted_player = fake_player(espn_id=42, position="RB")
    team = fake_team(roster=[drafted_player])
    pick = SimpleNamespace(
        round_num=1,
        round_pick=1,
        team=SimpleNamespace(team_id=team.team_id, team_name=team.team_name),
        playerId=42,
        playerName="Bijan Robinson",
    )
    result = _to_draft_pick(pick, player_lookup={42: _to_player(drafted_player)})
    assert result.player.position == "RB"
    assert result.team_name == "Giovanni's Grand Team"


def test_to_draft_pick_falls_back_when_player_not_in_lookup():
    pick = SimpleNamespace(
        round_num=2,
        round_pick=3,
        team=SimpleNamespace(team_id=1, team_name="Some Team"),
        playerId=99,
        playerName="Traded Away Guy",
    )
    result = _to_draft_pick(pick, player_lookup={})
    assert result.player.position == ""
    assert result.player.name == "Traded Away Guy"


def fake_settings(ppr=1.0):
    return SimpleNamespace(
        team_count=12,
        scoring_type="H2H_POINTS",
        scoring_format=[{"abbr": "REC", "points": ppr}, {"abbr": "RTD", "points": 6.0}],
        playoff_team_count=6,
        keeper_count=0,
        position_slot_counts={"QB": 1, "RB": 2, "BE": 4, "IR": 1, "": 0, "TQB": 0},
    )


def test_to_league_settings_extracts_ppr_and_nonzero_slots():
    settings = _to_league_settings(fake_settings(ppr=1.0))
    assert settings.points_per_reception == 1.0
    assert settings.position_slot_counts == {"QB": 1, "RB": 2, "BE": 4, "IR": 1}
    assert settings.team_count == 12


def test_to_league_settings_defaults_ppr_when_missing():
    espn_settings = fake_settings()
    espn_settings.scoring_format = [{"abbr": "RTD", "points": 6.0}]
    settings = _to_league_settings(espn_settings)
    assert settings.points_per_reception == 0.0


def fake_box_player(player_id, name="Box Player", points=10.0, slot="RB", position="RB", pro_team="ATL"):
    return SimpleNamespace(
        playerId=player_id, name=name, points=points, slot_position=slot, position=position, proTeam=pro_team
    )


def fake_matchup(home_id, away_id, home_lineup=None, away_lineup=None):
    return SimpleNamespace(
        home_team=SimpleNamespace(team_id=home_id) if home_id is not None else None,
        away_team=SimpleNamespace(team_id=away_id) if away_id is not None else None,
        home_lineup=home_lineup or [],
        away_lineup=away_lineup or [],
    )


def fake_client(reg_season_count, box_scores_by_week):
    return SimpleNamespace(
        settings=SimpleNamespace(reg_season_count=reg_season_count),
        box_scores=lambda week: box_scores_by_week.get(week, []),
    )


def test_enrich_adds_weekly_to_existing_roster_player():
    lookup = {10: Player(espn_id=10, name="X", position="RB", pro_team="ATL", total_points=999)}
    client = fake_client(
        2,
        {
            1: [fake_matchup(1, 2, home_lineup=[fake_box_player(10, points=12.0, slot="RB")])],
            2: [fake_matchup(1, 2, home_lineup=[fake_box_player(10, points=8.0, slot="BE")])],
        },
    )
    _enrich_with_weekly_performance(client, my_team_espn_id=1, player_lookup=lookup)

    assert [w.week for w in lookup[10].weekly] == [1, 2]
    assert lookup[10].weekly[0].points == 12.0
    assert lookup[10].weekly[1].slot == "BE"
    assert lookup[10].total_points == 20.0  # recomputed from weekly, not the original 999


def test_enrich_creates_entry_for_player_not_in_current_roster():
    lookup: dict[int, Player] = {}
    client = fake_client(
        1, {1: [fake_matchup(1, 2, home_lineup=[fake_box_player(99, name="Departed Guy", points=15.0)])]}
    )
    _enrich_with_weekly_performance(client, my_team_espn_id=1, player_lookup=lookup)

    assert 99 in lookup
    assert lookup[99].name == "Departed Guy"
    assert lookup[99].total_points == 15.0
    assert len(lookup[99].weekly) == 1


def test_enrich_uses_away_lineup_when_my_team_is_away():
    lookup: dict[int, Player] = {}
    client = fake_client(1, {1: [fake_matchup(2, 1, away_lineup=[fake_box_player(50, points=7.0)])]})
    _enrich_with_weekly_performance(client, my_team_espn_id=1, player_lookup=lookup)

    assert 50 in lookup
    assert lookup[50].total_points == 7.0


def test_enrich_ignores_matchups_not_involving_my_team():
    lookup: dict[int, Player] = {}
    client = fake_client(1, {1: [fake_matchup(2, 3, home_lineup=[fake_box_player(50, points=7.0)])]})
    _enrich_with_weekly_performance(client, my_team_espn_id=1, player_lookup=lookup)

    assert lookup == {}


def test_enrich_continues_past_a_week_that_errors():
    def box_scores(week):
        if week == 1:
            raise RuntimeError("ESPN hiccup")
        return [fake_matchup(1, 2, home_lineup=[fake_box_player(10, points=5.0)])]

    client = SimpleNamespace(settings=SimpleNamespace(reg_season_count=2), box_scores=box_scores)
    lookup: dict[int, Player] = {}
    _enrich_with_weekly_performance(client, my_team_espn_id=1, player_lookup=lookup)

    assert lookup[10].total_points == 5.0
    assert [w.week for w in lookup[10].weekly] == [2]


def fake_player_row(espn_id, name, points, stat_id="002025"):
    return {"player": {"id": espn_id, "fullName": name, "stats": [{"id": stat_id, "appliedTotal": points}]}}


def test_fetch_positional_rankings_sorts_by_points_and_assigns_rank():
    client = SimpleNamespace(
        finalScoringPeriod=17,
        espn_request=SimpleNamespace(
            league_get=lambda params, headers: {
                "players": [
                    fake_player_row(1, "Low", 50.0),
                    fake_player_row(2, "High", 300.0),
                    fake_player_row(3, "Mid", 150.0),
                ]
            }
        ),
    )
    result = _fetch_positional_rankings(client, 2025)

    qb = result["QB"]
    assert [r.name for r in qb] == ["High", "Mid", "Low"]
    assert [r.rank for r in qb] == [1, 2, 3]
    assert set(result.keys()) == {"QB", "RB", "WR", "TE", "D/ST", "K"}


def test_fetch_positional_rankings_continues_past_a_position_that_errors():
    calls = {"n": 0}

    def league_get(params, headers):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("ESPN hiccup")
        return {"players": [fake_player_row(1, "X", 10.0)]}

    client = SimpleNamespace(finalScoringPeriod=17, espn_request=SimpleNamespace(league_get=league_get))
    result = _fetch_positional_rankings(client, 2025)

    assert len(result) == 5  # one of the 6 positions failed
    assert calls["n"] == 6


def test_fetch_positional_rankings_uses_year_specific_stat_id():
    client = SimpleNamespace(
        finalScoringPeriod=17,
        espn_request=SimpleNamespace(
            league_get=lambda params, headers: {
                "players": [
                    fake_player_row(1, "Wrong Year", 999.0, stat_id="002024"),
                    fake_player_row(2, "Right Year", 42.0, stat_id="002025"),
                ]
            }
        ),
    )
    result = _fetch_positional_rankings(client, 2025)

    assert len(result["QB"]) == 2
    assert result["QB"][0].name == "Right Year"
    assert result["QB"][0].points == 42.0
    # "Wrong Year" has no matching stat entry, so its points default to 0.0
    assert result["QB"][1].points == 0.0
