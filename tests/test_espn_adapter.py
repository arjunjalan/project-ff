from types import SimpleNamespace

from app.adapters.espn import _to_draft_pick, _to_player, _to_team


def fake_player(espn_id=1, name="Bijan Robinson", position="RB", pro_team="ATL"):
    return SimpleNamespace(playerId=espn_id, name=name, position=position, proTeam=pro_team)


def fake_team(espn_id=1, roster=None):
    return SimpleNamespace(
        team_id=espn_id,
        team_name="Giovanni's Grand Team",
        owners=[{"displayName": "giovanni"}],
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
    player = _to_player(fake_player())
    assert player.espn_id == 1
    assert player.name == "Bijan Robinson"
    assert player.position == "RB"
    assert player.pro_team == "ATL"


def test_to_team_maps_owner_and_roster():
    team = _to_team(fake_team())
    assert team.owner == "giovanni"
    assert team.final_standing == 2
    assert len(team.roster) == 1
    assert team.roster[0].name == "Bijan Robinson"


def test_to_team_handles_no_owners():
    espn_team = fake_team()
    espn_team.owners = []
    team = _to_team(espn_team)
    assert team.owner is None


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
