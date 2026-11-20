import json

from conftest import BE, PG, TEAM_ID, TODAY
from test_server import APIKEY, SUPABASE, USER, api  # noqa: F401  (fixture)


def rpc(api, method, params=None, *, id=1, headers=USER):
    msg = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return api.post("/mcp", headers=headers, json=msg)


def call(api, name, headers=USER, **arguments):
    r = rpc(api, "tools/call", {"name": name, "arguments": arguments}, headers=headers)
    assert r.status_code == 200
    return r.json()["result"]


def test_needs_auth_and_points_to_oauth_metadata(api):
    r = api.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == (
        'Bearer resource_metadata="http://testserver/.well-known/oauth-protected-resource/mcp"')
    # Behind Vercel the public origin comes from the forwarded headers.
    r = api.post("/mcp", json={}, headers={"x-forwarded-proto": "https", "x-forwarded-host": "court.example"})
    assert "https://court.example/.well-known" in r.headers["www-authenticate"]
    # A bad token gets the same challenge.
    assert "resource_metadata" in api.post("/mcp", json={}, headers={"Authorization": "Bearer nope"}).headers[
        "www-authenticate"]


def test_protected_resource_metadata(api):
    for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
        assert api.get(path, headers={"x-forwarded-proto": "https", "host": "court.example"}).json() == {
            "resource": "https://court.example/mcp", "authorization_servers": [f"{SUPABASE}/auth/v1"],
            "bearer_methods_supported": ["header"], "resource_name": "Courtside"}


def test_consent_page(api, monkeypatch):
    assert api.get("/oauth/consent").status_code == 503  # no anon key configured
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    r = api.get("/oauth/consent", params={"authorization_id": "abc"})
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert json.dumps({"auth": f"{SUPABASE}/auth/v1", "anon": "anon-key"}) in r.text
    csp = r.headers["content-security-policy"]
    assert f"connect-src {SUPABASE};" in csp and "frame-ancestors 'none'" in csp and "script-src 'unsafe-inline'" in csp
    assert r.headers["cache-control"] == "no-store"


def test_initialize_negotiates_version(api):
    r = rpc(api, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                "clientInfo": {"name": "t", "version": "1"}}).json()["result"]
    assert r["protocolVersion"] == "2025-03-26" and "tools" in r["capabilities"]
    assert r["serverInfo"]["name"] == "courtside" and "checkup" in r["instructions"]
    assert rpc(api, "initialize", {"protocolVersion": "1999-01-01"}).json()["result"]["protocolVersion"] == "2025-06-18"


def test_notification_gets_202_and_unknown_method_errors(api):
    r = api.post("/mcp", headers=APIKEY, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status_code == 202 and r.content == b""
    assert rpc(api, "resources/list").json()["error"]["code"] == -32601
    assert api.post("/mcp", headers=APIKEY, content=b"{nope").json()["error"]["code"] == -32700
    assert api.post("/mcp", headers=APIKEY, json={"id": 1}).json()["error"]["code"] == -32600


def test_no_stream(api):
    assert api.get("/mcp", headers=APIKEY).status_code == 405


def test_tools_are_listed_and_only_confirm_writes(api):
    tools = {t["name"]: t for t in rpc(api, "tools/list").json()["result"]["tools"]}
    assert set(tools) == {
        "checkup", "get_roster", "get_scoreboard", "find_players", "get_league", "league_activity",
        "plan_lineup_move", "plan_roster_move", "confirm_move"}
    assert all(t["inputSchema"]["type"] == "object" for t in tools.values())
    assert [n for n, t in tools.items() if not t["annotations"]["readOnlyHint"]] == ["confirm_move"]
    assert tools["confirm_move"]["annotations"]["destructiveHint"]


def test_checkup(api):
    r = call(api, "checkup")
    body = r["structuredContent"]
    assert body["team"] == "Joe's Crepes" and body["day"] == TODAY
    # The fake roster fills 8 of 10 starting slots, with two bench players who have games.
    first = body["findings"][0]
    assert first["kind"] == "lineup" and first["message"].startswith("You can start 2 more players")
    assert {"empty_slot"} <= {f["kind"] for f in body["findings"]}
    # Days TODAY and TODAY+1 remain; only TODAY has games, and all ten slots can be filled.
    assert body["week"] == {"week": 1, "my_points": 120.5, "opponent": "Other Team", "opponent_points": 95.0,
                            "days_left": 2, "my_starts_left": 10, "opponent_starts_left": 0}
    assert body["pending_claims"] == [{"type": "WAIVER", "bid": 0, "expires": None, "items": ["ADD Waiver Will"]}]


def test_read_tools(api):
    roster = call(api, "get_roster")["structuredContent"]
    assert roster["id"] == TEAM_ID and len(roster["roster"]) == 11
    assert call(api, "get_roster", team_id=1)["structuredContent"]["name"] == "Other Team"
    board = call(api, "get_scoreboard")["structuredContent"]
    assert [m["mine"] for m in board["matchups"]] == [True]
    fa = call(api, "find_players", position="C")["structuredContent"]
    assert [p["name"] for p in fa["players"]] == ["Free Fred", "Waiver Will"]
    assert call(api, "get_league")["structuredContent"]["name"] == "Test League"
    act = call(api, "league_activity", limit=5)["structuredContent"]
    assert act["activity"] and act["pending"]


def test_text_content_mirrors_structured(api):
    import json
    r = call(api, "get_league")
    assert json.loads(r["content"][0]["text"]) == r["structuredContent"]


def test_tool_errors_are_results_not_protocol_errors(api):
    r = call(api, "get_roster", team_id=999)
    assert r["isError"] and "999" in r["content"][0]["text"]
    assert rpc(api, "tools/call", {"name": "nope"}).json()["error"]["code"] == -32602
    assert rpc(api, "tools/call", {"name": "checkup", "arguments": {"bogus": 1}}).json()["error"]["code"] == -32602


def test_espn_failure_is_a_tool_error(api, fake):
    fake.read_status = 401
    r = call(api, "checkup")
    assert r["isError"] and "ESPN_S2" in r["content"][0]["text"]


def test_batch(api):
    r = api.post("/mcp", headers=USER, json=[
        {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ])
    assert [m["id"] for m in r.json()] == [1, 2]


# ---- writes ----------------------------------------------------------------

def test_plan_then_confirm_lineup(api, fake):
    planned = call(api, "plan_lineup_move", player="bench ben", slot="PG")["structuredContent"]
    assert planned["summary"] == ["Bench Ben: BE -> PG", "Point Guard Paul: PG -> BE"]
    assert fake.posts == []  # planning changes nothing
    done = call(api, "confirm_move", plan=planned["plan"])["structuredContent"]
    assert done["status"] == "EXECUTED"
    assert [(i["playerId"], i["fromLineupSlotId"], i["toLineupSlotId"]) for i in fake.posts[0]["items"]] == [
        (109, BE, PG), (101, PG, BE)]


def test_plan_then_confirm_roster(api, fake):
    planned = call(api, "plan_roster_move", add=201, drop="bench bigs")["structuredContent"]
    assert planned["summary"] == ["Add Free Fred", "Drop Bench Bigs"]
    assert call(api, "confirm_move", plan=planned["plan"])["structuredContent"]["status"] == "EXECUTED"
    assert fake.posts[0]["type"] == "FREEAGENT"


def test_api_key_cannot_confirm(api, fake):
    planned = call(api, "plan_lineup_move", headers=APIKEY, player="bench ben", slot="PG")["structuredContent"]
    r = call(api, "confirm_move", headers=APIKEY, plan=planned["plan"])
    assert r["isError"] and "OAuth" in r["content"][0]["text"] and fake.posts == []


def test_caller_cannot_be_smuggled_in_arguments(api, fake):
    planned = call(api, "plan_lineup_move", player="bench ben", slot="PG")["structuredContent"]
    r = rpc(api, "tools/call", {"name": "confirm_move", "arguments": {"plan": planned["plan"], "who": "user"}},
            headers=APIKEY).json()
    assert r["error"]["code"] == -32602 and fake.posts == []


def test_confirm_refuses_a_stale_plan(api, fake):
    planned = call(api, "plan_lineup_move", player="bench ben", slot="PG")["structuredContent"]["plan"]
    planned["expect"][0]["toLineupSlotId"] = 11
    r = call(api, "confirm_move", plan=planned)
    assert r["isError"] and "nothing was submitted" in r["content"][0]["text"] and fake.posts == []


def test_confirm_with_writes_disabled_or_junk(api, fake, monkeypatch):
    planned = call(api, "plan_lineup_move", player="bench ben", slot="PG")["structuredContent"]["plan"]
    monkeypatch.setenv("ESPN_WRITE_ENABLED", "0")
    assert "ESPN_WRITE_ENABLED" in call(api, "confirm_move", plan=planned)["content"][0]["text"]
    assert call(api, "confirm_move", plan={"kind": "trade"})["isError"]
    assert call(api, "confirm_move", plan="yes please")["isError"]
    assert call(api, "confirm_move", plan={"kind": "lineup", "intent": {"expect": 1}})["isError"]
    assert fake.posts == []


def test_bad_plans_are_tool_errors(api):
    assert "not eligible" in call(api, "plan_lineup_move", player="center cal", slot="PG")["content"][0]["text"]
    assert call(api, "plan_roster_move")["isError"]
    r = rpc(api, "tools/call", {"name": "plan_lineup_move", "arguments": {"player": "ben"}}).json()
    assert r["error"]["code"] == -32602 and "slot" in r["error"]["message"]
