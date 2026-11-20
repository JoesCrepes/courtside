from conftest import TEAM_ID, TODAY
from test_server import APIKEY, USER, api  # noqa: F401  (fixture)


def rpc(api, method, params=None, *, id=1, headers=APIKEY):
    msg = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return api.post("/mcp", headers=headers, json=msg)


def call(api, name, **arguments):
    r = rpc(api, "tools/call", {"name": name, "arguments": arguments})
    assert r.status_code == 200
    return r.json()["result"]


def test_needs_auth(api):
    assert api.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 401


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


def test_tools_are_listed_read_only(api):
    tools = rpc(api, "tools/list").json()["result"]["tools"]
    assert {t["name"] for t in tools} == {
        "checkup", "get_roster", "get_scoreboard", "find_players", "get_league", "league_activity"}
    assert all(t["annotations"]["readOnlyHint"] and t["inputSchema"]["type"] == "object" for t in tools)


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
