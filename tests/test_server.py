import pytest
from fastapi.testclient import TestClient

from server.app import app

from conftest import LEAGUE_ID, SEASON, SWID, TEAM_ID

KEY = "test-key"


@pytest.fixture
def api(monkeypatch, fake):
    monkeypatch.setenv("COURTSIDE_API_KEY", KEY)
    monkeypatch.setenv("ESPN_LEAGUE_ID", str(LEAGUE_ID))
    monkeypatch.setenv("ESPN_SEASON", str(SEASON))
    monkeypatch.setenv("ESPN_TEAM_ID", str(TEAM_ID))
    monkeypatch.setenv("ESPN_S2", "AEfakeS2cookie")
    monkeypatch.setenv("ESPN_SWID", SWID)
    return TestClient(app)


def test_health_needs_no_key(api):
    assert api.get("/health").json() == {"ok": True}


def test_roster_needs_key(api):
    assert api.get("/roster").status_code == 401
    assert api.get("/roster", params={"key": "wrong"}).status_code == 401


def test_missing_key_config_fails_closed(api, monkeypatch):
    monkeypatch.delenv("COURTSIDE_API_KEY")
    assert api.get("/roster", params={"key": ""}).status_code == 503


def test_roster(api, fake):
    r = api.get("/roster", headers={"Authorization": f"Bearer {KEY}"}, params={"day": 9})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Joe's Crepes"
    ivan = next(p for p in body["roster"] if p["name"] == "Injured Ivan")
    assert ivan["slot"] == "IR" and ivan["is_starting"] is False
    assert "scoringPeriodId=9" in fake.rsps.calls[-1].request.url


def test_espn_failure_is_502(api, fake):
    fake.read_status = 401
    r = api.get("/roster", params={"key": KEY})
    assert r.status_code == 502
    assert "ESPN_S2" in r.json()["detail"]
