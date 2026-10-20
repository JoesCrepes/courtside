import json

import pytest

from courtside import Config, EspnClient, EspnError, EspnWriteError
from courtside.slots import slot_id

from conftest import BE, PG, SWID, TEAM_ID, TODAY


def test_reads_send_auth_cookies(client, fake):
    client.current_scoring_period()
    cookie = fake.rsps.calls[0].request.headers["Cookie"]
    assert "espn_s2=AEfakeS2cookie" in cookie
    assert f"SWID={SWID}" in cookie


def test_current_scoring_period(client):
    assert client.current_scoring_period() == TODAY


def test_team_parses_roster(client):
    team = client.team()
    assert team.name == "Joe's Crepes"
    assert len(team.roster) == 11
    assert team.find("ivan").injury_status == "OUT"
    assert sum(p.is_starting for p in team.roster) == 8


def test_team_name_falls_back_to_location_nickname(client):
    assert client.team(1).name == "Other Team"


def test_find_ambiguous_name(client):
    with pytest.raises(KeyError, match="matched 2"):
        client.team().find("bench")


def test_scoring_period_is_forwarded(client, fake):
    client.team(scoring_period=9)
    assert "scoringPeriodId=9" in fake.rsps.calls[-1].request.url


def test_free_agents_filter_header(client, fake):
    fas = client.free_agents(limit=10, position="c")
    assert [p.name for p in fas] == ["Free Fred", "Waiver Will"]
    assert fas[1].injury_status == "DAY_TO_DAY"
    filt = json.loads(fake.rsps.calls[-1].request.headers["x-fantasy-filter"])
    assert filt["players"]["limit"] == 10
    assert filt["players"]["filterSlotIds"] == {"value": [4]}
    assert filt["players"]["filterStatus"] == {"value": ["FREEAGENT", "WAIVERS"]}


def test_private_league_without_cookies(fake):
    fake.read_status = 401
    c = EspnClient(Config(league_id=123456, season=2027))
    with pytest.raises(EspnError, match="ESPN_S2"):
        c.current_scoring_period()


# ---- write safety ----------------------------------------------------------

def test_submit_is_dry_run_by_default(client, fake):
    out = client.add_drop(201, None)
    assert out["dry_run"] is True
    assert out["url"] == fake.writes_url
    assert fake.posts == []


def test_execute_still_dry_when_writes_disabled(config, fake):
    c = EspnClient(Config(**{**config.__dict__, "write_enabled": False}))
    out = c.add_drop(201, None, execute=True)
    assert out["dry_run"] is True and "ESPN_WRITE_ENABLED" in out["reason"]
    assert fake.posts == []


def test_execute_posts_payload(client, fake):
    out = client.add_drop(201, 110, execute=True)
    assert out == {"id": "txn-1", "status": "EXECUTED"}
    assert len(fake.posts) == 1
    body = fake.posts[0]
    assert body["type"] == "FREEAGENT"
    assert body["scoringPeriodId"] == TODAY
    assert body["memberId"] == SWID
    assert fake.rsps.calls[-1].request.headers["Content-Type"] == "application/json"


def test_write_error_surfaces_espn_messages(client, fake):
    fake.write_status = 409
    fake.write_body = {"messages": [{"message": "Roster is full"}]}
    with pytest.raises(EspnWriteError, match="Roster is full") as e:
        client.add_drop(201, None, execute=True)
    assert e.value.status == 409


def test_waiver_requires_add(client):
    with pytest.raises(ValueError):
        client.add_drop(None, 110, waiver=True)


# ---- end to end lineup move ------------------------------------------------

def test_move_end_to_end(client, fake):
    out = client.move("bench ben", slot_id("PG"), execute=True)
    assert out["status"] == "EXECUTED"
    body = fake.posts[0]
    assert body["type"] == "ROSTER"
    assert body["scoringPeriodId"] == TODAY
    assert [(i["playerId"], i["fromLineupSlotId"], i["toLineupSlotId"]) for i in body["items"]] == [
        (109, BE, PG),
        (101, PG, BE),
    ]
    assert all(i["fromTeamId"] == i["toTeamId"] == TEAM_ID for i in body["items"])


def test_move_future_day_uses_that_period(client, fake):
    out = client.move("109", slot_id("util"), scoring_period=7)
    assert out["dry_run"] is True
    assert out["payload"]["scoringPeriodId"] == 7
    assert out["payload"]["items"] == [
        {"playerId": 109, "type": "LINEUP", "fromTeamId": TEAM_ID, "fromLineupSlotId": BE,
         "toTeamId": TEAM_ID, "toLineupSlotId": 11}
    ]
