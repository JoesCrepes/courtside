"""MCP endpoint (POST /mcp) so Claude can read the league as tools.

This is the stateless slice of MCP's Streamable HTTP transport: each POST
carries one JSON-RPC message and gets one JSON reply, with no sessions and
no server-sent events. That fits Vercel, where nothing outlives a request.
Methods: initialize, ping, tools/list, tools/call. Notifications get 202.

Auth is the same bearer token as the REST routes (server/auth.py). Every tool
here only reads; writes stay on the REST preview -> confirm routes for now.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from courtside import EspnClient, EspnError
from courtside.checkup import Finding, check_day, games_left, remaining_days
from courtside.transactions import LineupError, slot_counts_from_settings

from . import app as rest
from .auth import caller

router = APIRouter()

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")  # newest first
INSTRUCTIONS = (
    "Tools for managing one ESPN fantasy basketball team (the user's). Start with `checkup`: it lists what "
    "needs attention today and this week. Days are ESPN scoring periods (one per day of the season) and weeks "
    "are matchup periods; omit them for today and this week. Fantasy averages are points per game. "
    "These tools only read; tell the user what to change rather than claiming you changed it."
)


# ---- tools -----------------------------------------------------------------

def _checkup(client: EspnClient, day: int | None = None) -> dict:
    status = client.status()
    day = day or status["scoring_period"]
    week = status["matchup_period"]
    settings = client.settings()
    counts = slot_counts_from_settings(settings)
    teams = {t.id: t for t in client.teams(scoring_period=day)}
    me = teams.get(client.config.team_id)  # type: ignore[arg-type]
    if me is None:
        raise EspnError(f"team {client.config.team_id} not found; check ESPN_TEAM_ID")
    sched = client.pro_schedule()
    findings = check_day(me, sched, day, counts)

    matchup = next((m for m in client.scoreboard(week) if me.id in (m.home_team_id, m.away_team_id)), None)
    week_info: dict[str, Any] = {"week": week}
    if matchup:
        home = matchup.home_team_id == me.id
        opp = teams.get(matchup.away_team_id if home else matchup.home_team_id)
        days = remaining_days(settings, week, day)
        mine = games_left(me, sched, days, counts, day)
        week_info.update({
            "my_points": matchup.home_points if home else matchup.away_points,
            "opponent": opp.name if opp else None,
            "opponent_points": (matchup.away_points if home else matchup.home_points) if opp else None,
            "days_left": len(days),
            "my_starts_left": mine,
        })
        if opp and days:
            theirs = games_left(opp, sched, days, counts, day)
            week_info["opponent_starts_left"] = theirs
            if theirs - mine >= 2:
                findings.append(Finding(
                    "warning", "games_behind",
                    f"{opp.name} can make {theirs - mine} more starts than you over the rest of the week. "
                    "A free agent with games on your open days would close the gap."))

    names = client.player_names()
    pending = [
        {"type": t.get("type"), "bid": t.get("bidAmount"), "expires": t.get("expirationDate"),
         "items": [f"{i.get('type')} {names.get(i.get('playerId'), i.get('playerId'))}" for i in t.get("items", [])]}
        for t in client.pending() if t.get("teamId") == me.id
    ]
    return {
        "team": me.name, "day": day, "week": week_info,
        "findings": [f.to_json() for f in findings],
        "pending_claims": pending,
    }


def _roster(client: EspnClient, day: int | None = None, team_id: int | None = None) -> dict:
    return rest._roster(client, team_id, day)


def _scoreboard(client: EspnClient, week: int | None = None) -> dict:
    body = rest.scoreboard(week, client)
    for m in body["matchups"]:
        m["mine"] = client.config.team_id in {s["team_id"] for s in (m["home"], m["away"]) if s}
    return body


def _players(
    client: EspnClient, query: str | None = None, position: str | None = None, available: bool = True,
    limit: int = 25, day: int | None = None,
) -> dict:
    return rest.players(q=query, pos=position, available=available, limit=limit, offset=0, day=day, client=client)


def _league(client: EspnClient) -> dict:
    return rest.league(client)


def _activity(client: EspnClient, limit: int = 25) -> dict:
    return {**rest.activity(limit, client), **rest.pending(client)}


_DAY = {"type": "integer", "minimum": 1, "description": "ESPN scoring period (day). Omit for today."}
_WEEK = {"type": "integer", "minimum": 1, "description": "Matchup period (week). Omit for this week."}

TOOLS: dict[str, tuple[Callable[..., dict], dict]] = {
    "checkup": (_checkup, {
        "title": "Team checkup",
        "description": "What needs attention: lineup holes, starters without a game or injured, IR problems, "
                       "starts left this week versus the opponent, and pending waiver claims. Start here.",
        "inputSchema": {"type": "object", "properties": {"day": _DAY}},
    }),
    "get_roster": (_roster, {
        "title": "Roster",
        "description": "A roster for a day: each player's slot, positions, injury status, fantasy averages "
                       "(last 7/15/30 days, season, projected) and NBA game that day. Defaults to the user's team.",
        "inputSchema": {"type": "object", "properties": {
            "day": _DAY, "team_id": {"type": "integer", "description": "Another team's id (see get_league)."}}},
    }),
    "get_scoreboard": (_scoreboard, {
        "title": "Scoreboard",
        "description": "Every matchup in a week with live points. The user's matchup has mine=true.",
        "inputSchema": {"type": "object", "properties": {"week": _WEEK}},
    }),
    "find_players": (_players, {
        "title": "Find players",
        "description": "Free agents and waiver players, most-owned first, or any player by name with "
                       "available=false. Includes averages and each player's game that day.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Name or part of one."},
            "position": {"type": "string", "description": "PG, SG, SF, PF, C, G, F or UTIL."},
            "available": {"type": "boolean", "default": True, "description": "False to include rostered players."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            "day": _DAY}},
    }),
    "get_league": (_league, {
        "title": "League",
        "description": "League settings (scoring, lineup slots, acquisition limits and budget) and standings "
                       "with each team's id.",
        "inputSchema": {"type": "object", "properties": {}},
    }),
    "league_activity": (_activity, {
        "title": "League activity",
        "description": "Recent adds, drops, trades and lineup moves across the league, plus pending waiver "
                       "claims and trades.",
        "inputSchema": {"type": "object", "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25}}},
    }),
}


def _tool_list() -> list[dict]:
    return [{"name": name, **spec, "annotations": {"readOnlyHint": True, "openWorldHint": True}}
            for name, (_, spec) in TOOLS.items()]


def _call(client: EspnClient, params: dict) -> dict:
    name, args = params.get("name"), params.get("arguments") or {}
    if name not in TOOLS:
        raise _RpcError(-32602, f"unknown tool {name!r}")
    fn, spec = TOOLS[name]
    allowed = spec["inputSchema"]["properties"]
    unknown = set(args) - set(allowed)
    if unknown:
        raise _RpcError(-32602, f"unknown argument(s) for {name}: {', '.join(sorted(unknown))}")
    try:
        result = fn(client, **args)
    except (EspnError, LineupError, KeyError, ValueError) as e:
        # Tool failures go back to the model as results it can read and act on.
        msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
        return {"content": [{"type": "text", "text": msg}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result}


# ---- JSON-RPC --------------------------------------------------------------

class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        self.code, self.message = code, message


def _handle(msg: Any, client_factory: Callable[[], EspnClient]) -> dict | None:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                "error": {"code": -32600, "message": "invalid JSON-RPC request"}}
    if "id" not in msg:
        return None  # a notification (e.g. notifications/initialized): nothing to say
    method, params = msg["method"], msg.get("params") or {}
    try:
        if method == "initialize":
            asked = params.get("protocolVersion")
            result: dict = {
                "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "courtside", "title": "Courtside fantasy basketball", "version": "0.1.0"},
                "instructions": INSTRUCTIONS,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": _tool_list()}
        elif method == "tools/call":
            result = _call(client_factory(), params)
        else:
            raise _RpcError(-32601, f"method not found: {method}")
    except _RpcError as e:
        return {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": e.code, "message": e.message}}
    return {"jsonrpc": "2.0", "id": msg["id"], "result": result}


@router.post("/mcp", dependencies=[Depends(caller)])
async def mcp(request: Request) -> Response:
    try:
        body = json.loads(await request.body())
    except ValueError:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
    # The client is built lazily so initialize and tools/list work without ESPN settings.
    factory = rest.get_client
    # ESPN calls block, so run them off the event loop like FastAPI does for sync routes.
    if isinstance(body, list):  # a batch (2025-03-26 and earlier)
        replies = [r for m in body if (r := await run_in_threadpool(_handle, m, factory)) is not None]
        return JSONResponse(replies) if replies else Response(status_code=202)
    reply = await run_in_threadpool(_handle, body, factory)
    return JSONResponse(reply) if reply is not None else Response(status_code=202)


@router.get("/mcp")
@router.delete("/mcp")
def mcp_no_stream() -> Response:
    # No server-initiated stream and no sessions to end.
    return Response(status_code=405, headers={"Allow": "POST"})
