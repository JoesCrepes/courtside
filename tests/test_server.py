import json
import time

import jwt
import pytest
import responses
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from server import auth
from server.app import app

from conftest import BE, LEAGUE_ID, PG, SEASON, SWID, TEAM_ID, TODAY

KEY = "test-api-key"
SUPABASE = "https://proj.supabase.co"
ME = "joe@example.com"


def _keypair(kid: str):
    private = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    return private, {**public_jwk, "kid": kid, "alg": "ES256", "use": "sig"}


SIGNING_KEY, SIGNING_JWK = _keypair("k1")
OTHER_KEY, _ = _keypair("k1")  # same kid, different key: a forgery


def token(email: str = ME, *, key=SIGNING_KEY, kid: str = "k1", exp: int | None = None, aud: str = "authenticated"):
    claims = {
        "sub": "user-1", "email": email, "aud": aud, "iss": f"{SUPABASE}/auth/v1",
        "exp": exp if exp is not None else int(time.time()) + 3600,
    }
    return jwt.encode(claims, key, algorithm="ES256", headers={"kid": kid})


def bearer(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def api(monkeypatch, fake):
    for k, v in {
        "COURTSIDE_API_KEY": KEY, "SUPABASE_URL": SUPABASE, "COURTSIDE_ALLOWED_EMAILS": f"{ME}, other@x.com",
        "ESPN_LEAGUE_ID": str(LEAGUE_ID), "ESPN_SEASON": str(SEASON), "ESPN_TEAM_ID": str(TEAM_ID),
        "ESPN_S2": "AEfakeS2cookie", "ESPN_SWID": SWID, "ESPN_WRITE_ENABLED": "1",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(auth, "_jwks", {})
    fake.rsps.add(responses.GET, f"{SUPABASE}/auth/v1/.well-known/jwks.json", json={"keys": [SIGNING_JWK]})
    return TestClient(app)


USER = bearer(token())
APIKEY = bearer(KEY)


# ---- auth ------------------------------------------------------------------

def test_health_needs_no_auth(api):
    assert api.get("/health").json() == {"ok": True}


@pytest.mark.parametrize("headers,status", [
    ({}, 401),
    (bearer("wrong-key"), 401),
    (bearer(token("stranger@x.com")), 403),
    (bearer(token(exp=int(time.time()) - 10)), 401),
    (bearer(token(aud="anon")), 401),
    (bearer(token(key=OTHER_KEY)), 401),
    (bearer(token(kid="unknown")), 401),
])
def test_rejected_callers(api, headers, status):
    assert api.get("/roster", headers=headers).status_code == status


def test_user_and_api_key_can_read(api):
    assert api.get("/context", headers=USER).json()["caller"] == "user"
    assert api.get("/context", headers=APIKEY).json()["caller"] == "key"


def test_allowed_email_is_case_insensitive(api):
    assert api.get("/roster", headers=bearer(token("JOE@Example.com"))).status_code == 200


def test_missing_auth_config_fails_closed(api, monkeypatch):
    monkeypatch.delenv("COURTSIDE_ALLOWED_EMAILS")
    assert api.get("/roster", headers=USER).status_code == 503
    monkeypatch.delenv("COURTSIDE_API_KEY")
    assert api.get("/roster", headers=APIKEY).status_code == 503


def test_api_key_cannot_write(api, fake):
    body = {"player": "bench ben", "slot": "PG", "expect": [], "scoring_period": TODAY}
    assert api.post("/lineup/confirm", headers=APIKEY, json=body).status_code == 403
    assert fake.posts == []


# ---- reads -----------------------------------------------------------------

def test_context(api):
    ctx = api.get("/context", headers=USER).json()
    assert ctx["scoring_period"] == TODAY and ctx["team_id"] == TEAM_ID and ctx["email"] == ME


def test_roster_has_games_positions_and_stats(api, fake):
    body = api.get("/roster", headers=USER).json()
    assert body["name"] == "Joe's Crepes" and body["day"] == TODAY and body["wins"] == 1
    paul = next(p for p in body["roster"] if p["name"] == "Point Guard Paul")
    assert paul["positions"] == ["PG"] and paul["slot"] == "PG" and paul["is_starting"]
    assert paul["pro_team"] == "BOS"
    assert paul["game"] == {"id": 9001, "start": 1792000000000, "home": True, "opponent": "NYK"}
    off_day = api.get("/roster", headers=USER, params={"day": 5}).json()
    assert all(p["game"] is None for p in off_day["roster"])
    assert "scoringPeriodId=5" in fake.rsps.calls[-1].request.url or any(
        "scoringPeriodId=5" in c.request.url for c in fake.rsps.calls)


def test_other_team(api):
    assert api.get("/teams/1", headers=USER).json()["name"] == "Other Team"


def test_league(api):
    body = api.get("/league", headers=USER).json()
    assert body["slots"]["UTIL"] == 3 and "SG/SF" not in body["slots"]
    assert [t["id"] for t in body["standings"]] == [TEAM_ID, 1]


def test_scoreboard_defaults_to_current_week_with_live_points(api):
    body = api.get("/scoreboard", headers=USER).json()
    assert body["week"] == 1 and len(body["matchups"]) == 1
    m = body["matchups"][0]
    assert m["home"] == {"team_id": TEAM_ID, "name": "Joe's Crepes", "points": 120.5}
    assert api.get("/scoreboard", headers=USER, params={"week": 2}).json()["matchups"][0]["away"]["points"] == 0.0


def test_player_search_sends_name_filter(api, fake):
    api.get("/players", headers=USER, params={"q": "fred", "available": "false"})
    req = next(c.request for c in reversed(fake.rsps.calls) if "kona_player_info" in c.request.url)
    filt = json.loads(req.headers["x-fantasy-filter"])["players"]
    assert filt["filterName"] == {"value": "fred"} and filt["filterActive"] == {"value": True}
    assert "filterStatus" not in filt


def test_free_agents(api):
    body = api.get("/players", headers=USER, params={"pos": "C"}).json()
    will = body["players"][1]
    assert will["name"] == "Waiver Will" and will["status"] == "WAIVERS" and will["slot"] is None


def test_activity(api):
    acts = api.get("/activity", headers=USER).json()["activity"]
    assert acts[0]["items"][0] == {"kind": "MOVE", "player_id": 109, "player": "Bench Ben", "team_id": TEAM_ID,
                                   "from_slot": "BE", "to_slot": "PG"}
    assert [(i["kind"], i["player"]) for i in acts[1]["items"]] == [("ADD", "Free Fred"), ("DROP", "Bench Bigs")]


def test_pending(api):
    p = api.get("/pending", headers=USER).json()["pending"][0]
    assert p["type"] == "WAIVER" and p["items"][0]["player"] == "Waiver Will"


def test_espn_failure_is_502(api, fake):
    fake.read_status = 401
    r = api.get("/roster", headers=USER)
    assert r.status_code == 502 and "ESPN_S2" in r.json()["detail"]


# ---- writes ----------------------------------------------------------------

LINEUP = {"player": "bench ben", "slot": "PG"}


def test_lineup_preview_does_not_post(api, fake):
    pv = api.post("/lineup/preview", headers=USER, json=LINEUP).json()
    assert pv["summary"] == ["Bench Ben: BE -> PG", "Point Guard Paul: PG -> BE"]
    assert pv["scoring_period"] == TODAY and "memberId" not in json.dumps(pv)
    assert fake.posts == []


def test_lineup_confirm_executes_preview(api, fake):
    pv = api.post("/lineup/preview", headers=USER, json=LINEUP).json()
    r = api.post("/lineup/confirm", headers=USER, json={**LINEUP, "expect": pv["expect"], "scoring_period": TODAY})
    assert r.status_code == 200 and r.json()["status"] == "EXECUTED"
    assert len(fake.posts) == 1
    assert [(i["playerId"], i["fromLineupSlotId"], i["toLineupSlotId"]) for i in fake.posts[0]["items"]] == [
        (109, BE, PG), (101, PG, BE)]


def test_confirm_refuses_a_stale_plan(api, fake):
    stale = [{"playerId": 109, "type": "LINEUP", "fromLineupSlotId": BE, "toLineupSlotId": 11}]
    r = api.post("/lineup/confirm", headers=USER, json={**LINEUP, "expect": stale, "scoring_period": TODAY})
    assert r.status_code == 409
    assert r.json()["detail"]["preview"]["summary"][0] == "Bench Ben: BE -> PG"
    assert fake.posts == []


def test_confirm_refuses_another_day(api, fake):
    pv = api.post("/lineup/preview", headers=USER, json=LINEUP).json()
    r = api.post("/lineup/confirm", headers=USER, json={**LINEUP, "expect": pv["expect"], "scoring_period": TODAY - 1})
    assert r.status_code == 409 and fake.posts == []


def test_confirm_when_server_writes_disabled(api, fake, monkeypatch):
    monkeypatch.setenv("ESPN_WRITE_ENABLED", "0")
    pv = api.post("/lineup/preview", headers=USER, json=LINEUP).json()
    r = api.post("/lineup/confirm", headers=USER, json={**LINEUP, "expect": pv["expect"], "scoring_period": TODAY})
    assert r.status_code == 503 and fake.posts == []


def test_bad_move_is_400(api):
    r = api.post("/lineup/preview", headers=USER, json={"player": "center cal", "slot": "PG"})
    assert r.status_code == 400 and "not eligible" in r.json()["detail"]
    r = api.post("/lineup/preview", headers=USER, json={"player": "nobody", "slot": "PG"})
    assert r.status_code == 400 and "matched 0" in r.json()["detail"]


def test_roster_add_drop(api, fake):
    intent = {"add": 201, "drop": "bigs"}
    pv = api.post("/roster/preview", headers=USER, json=intent).json()
    assert pv["type"] == "FREEAGENT" and pv["summary"] == ["Add Free Fred", "Drop Bench Bigs"]
    r = api.post("/roster/confirm", headers=USER, json={**intent, "expect": pv["expect"], "scoring_period": TODAY})
    assert r.status_code == 200 and fake.posts[0]["type"] == "FREEAGENT"


def test_waiver_claim_preview(api):
    pv = api.post("/roster/preview", headers=USER, json={"add": 202, "waiver": True, "bid": 3}).json()
    assert pv["type"] == "WAIVER" and pv["summary"] == ["Claim Waiver Will (bid $3)"]


def test_espn_rejection_is_422(api, fake):
    fake.write_status = 409
    fake.write_body = {"messages": [{"message": "Roster is full"}]}
    intent = {"add": 201}
    pv = api.post("/roster/preview", headers=USER, json=intent).json()
    r = api.post("/roster/confirm", headers=USER, json={**intent, "expect": pv["expect"], "scoring_period": TODAY})
    assert r.status_code == 422 and "Roster is full" in r.json()["detail"]
