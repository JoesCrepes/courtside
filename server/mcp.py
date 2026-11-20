"""MCP endpoint (POST /mcp) so Claude can read the league as tools.

This is the stateless slice of MCP's Streamable HTTP transport: each POST
carries one JSON-RPC message and gets one JSON reply, with no sessions and
no server-sent events. That fits Vercel, where nothing outlives a request.
Methods: initialize, ping, tools/list, tools/call. Notifications get 202.

Auth is the same bearer token as the REST routes (server/auth.py): an OAuth
token from Supabase (see server/oauth.py) or COURTSIDE_API_KEY. A 401 names
the OAuth metadata so clients can start sign-in. Writes are two tools, like
the REST preview -> confirm: plan_* returns a plan and changes nothing, and
confirm_move submits it, only for a signed-in user, and only if a fresh
re-plan still matches.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from courtside import EspnClient, EspnError
from courtside.checkup import Finding, check_day, day_date, first_day, games_left, matchup_days
from courtside.transactions import LineupError, slot_counts_from_settings

from . import app as rest
from .auth import Caller, caller
from .oauth import resource_metadata_url

router = APIRouter()

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")  # newest first
INSTRUCTIONS = (
    "Tools for managing one ESPN fantasy basketball team (the user's). Start with `checkup`: it lists what "
    "needs attention today and this week. Days are ESPN scoring periods (one per day of the season) and weeks "
    "are matchup periods; omit them for today and this week. Fantasy averages are points per game. "
    "To change the lineup or roster, call plan_lineup_move or plan_roster_move, show the user the plan's "
    "summary, and call confirm_move with that plan only after they say yes. Never confirm without a yes."
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
        all_days = matchup_days(settings, sched, week)
        days = [d for d in all_days if d >= day]
        mine = games_left(me, sched, days, counts, day)
        start = first_day(sched)
        if start and all_days:
            week_info.update({
                "first_day": all_days[0], "last_day": all_days[-1],
                "start": day_date(start, all_days[0]).isoformat(), "end": day_date(start, all_days[-1]).isoformat(),
            })
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


def _plan(kind: str, intent: dict, payload: dict, client: EspnClient) -> dict:
    preview = rest._preview(client, payload)
    return {"summary": preview["summary"], "plan": {
        "kind": kind, "intent": intent, "expect": preview["expect"], "scoring_period": preview["scoring_period"]}}


def _plan_lineup(client: EspnClient, player: str, slot: str, swap_with: str | None = None,
                 day: int | None = None) -> dict:
    intent = rest.LineupIntent(player=player, slot=slot, swap_with=swap_with, day=day)
    return _plan("lineup", intent.model_dump(), rest._plan_lineup(client, intent), client)


def _plan_roster(client: EspnClient, add: int | None = None, drop: str | None = None, waiver: bool = False,
                 bid: int | None = None) -> dict:
    if add is None and drop is None:
        raise ValueError("give a player to add, a player to drop, or both")
    intent = rest.RosterIntent(add=add, drop=drop, waiver=waiver, bid=bid)
    return _plan("roster", intent.model_dump(), rest._plan_roster(client, intent), client)


def _confirm(client: EspnClient, plan: dict, *, who: Caller) -> dict:
    if not who.can_write:
        raise ValueError("Changing the team needs a signed-in user. This connector is using the read-only API "
                         "key; reconnect it with OAuth sign-in.")
    if not isinstance(plan, dict):
        raise ValueError("plan must be the `plan` object returned by plan_lineup_move or plan_roster_move")
    kind = plan.get("kind")
    fields = {**(plan.get("intent") or {}), "expect": plan.get("expect"), "scoring_period": plan.get("scoring_period")}
    if kind == "lineup":
        body: Any = rest.LineupConfirm(**fields)
        payload = rest._plan_lineup(client, body)
    elif kind == "roster":
        body = rest.RosterConfirm(**fields)
        payload = rest._plan_roster(client, body)
    else:
        raise ValueError("plan must be the `plan` object returned by plan_lineup_move or plan_roster_move")
    try:
        return rest._confirm(client, payload, body)
    except HTTPException as e:
        if e.status_code == 409:
            raise ValueError("The team changed since this plan was made, so nothing was submitted. "
                             f"Fresh plan: {json.dumps(e.detail['preview'])}") from None
        raise ValueError(str(e.detail)) from None


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
        "description": "League settings (scoring, lineup slots, acquisition limits and budget), today's day "
                       "and week, every week's first and last day with dates, and standings with each team's id.",
        "inputSchema": {"type": "object", "properties": {}},
    }),
    "league_activity": (_activity, {
        "title": "League activity",
        "description": "Recent adds, drops, trades and lineup moves across the league, plus pending waiver "
                       "claims and trades.",
        "inputSchema": {"type": "object", "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25}}},
    }),
    "plan_lineup_move": (_plan_lineup, {
        "title": "Plan a lineup move",
        "description": "Work out how to put a player in a lineup slot (swapping or benching whoever is there, "
                       "as ESPN's MOVE button does). Changes nothing; returns a summary and a plan for "
                       "confirm_move.",
        "inputSchema": {"type": "object", "required": ["player", "slot"], "properties": {
            "player": {"type": "string", "description": "Rostered player's name (or part of it) or id."},
            "slot": {"type": "string", "description": "PG, SG, SF, PF, C, G, F, UTIL, BE or IR."},
            "swap_with": {"type": "string", "description": "Which occupant gives up the slot, if it's full."},
            "day": _DAY}},
    }),
    "plan_roster_move": (_plan_roster, {
        "title": "Plan an add, drop or claim",
        "description": "Work out adding a free agent, dropping a player, or both, or a waiver claim. Changes "
                       "nothing; returns a summary and a plan for confirm_move. Get ids from find_players.",
        "inputSchema": {"type": "object", "properties": {
            "add": {"type": "integer", "description": "Player id to add (from find_players)."},
            "drop": {"type": "string", "description": "Rostered player to drop: name (or part of it) or id."},
            "waiver": {"type": "boolean", "default": False, "description": "Claim off waivers instead."},
            "bid": {"type": "integer", "minimum": 0, "description": "FAAB bid for a waiver claim."}}},
    }),
    "confirm_move": (_confirm, {
        "title": "Submit a planned move",
        "description": "Submit a plan from plan_lineup_move or plan_roster_move to ESPN. Only call this after "
                       "the user has seen the plan's summary and said yes. Fails without changing anything "
                       "if the team changed since the plan was made.",
        "inputSchema": {"type": "object", "required": ["plan"], "properties": {
            "plan": {"type": "object", "description": "The `plan` object from a plan_* tool, unchanged."}}},
    }),
}

# Tools that change the team; the rest only read ESPN.
WRITES = {"confirm_move"}


def _tool_list() -> list[dict]:
    return [{"name": name, **spec, "annotations": {
                "readOnlyHint": name not in WRITES, "destructiveHint": name in WRITES,
                "idempotentHint": False, "openWorldHint": True}}
            for name, (_, spec) in TOOLS.items()]


def _call(client: EspnClient, who: Caller, params: dict) -> dict:
    name, args = params.get("name"), params.get("arguments") or {}
    if name not in TOOLS:
        raise _RpcError(-32602, f"unknown tool {name!r}")
    fn, spec = TOOLS[name]
    allowed = spec["inputSchema"]["properties"]
    unknown = set(args) - set(allowed)
    if unknown:
        raise _RpcError(-32602, f"unknown argument(s) for {name}: {', '.join(sorted(unknown))}")
    missing = set(spec["inputSchema"].get("required", [])) - set(args)
    if missing:
        raise _RpcError(-32602, f"missing argument(s) for {name}: {', '.join(sorted(missing))}")
    try:
        result = fn(client, **args, who=who) if name in WRITES else fn(client, **args)
    except (EspnError, LineupError, KeyError, ValueError) as e:
        # Tool failures go back to the model as results it can read and act on.
        msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
        return {"content": [{"type": "text", "text": msg}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result}


# ---- JSON-RPC --------------------------------------------------------------

class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        self.code, self.message = code, message


def _handle(msg: Any, client_factory: Callable[[], EspnClient], who: Caller) -> dict | None:
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
            result = _call(client_factory(), who, params)
        else:
            raise _RpcError(-32601, f"method not found: {method}")
    except _RpcError as e:
        return {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": e.code, "message": e.message}}
    return {"jsonrpc": "2.0", "id": msg["id"], "result": result}


def mcp_caller(request: Request) -> Caller:
    try:
        return caller(request)
    except HTTPException as e:
        if e.status_code == 401:  # tell the client where to sign in (MCP auth spec)
            e.headers = {"WWW-Authenticate": f'Bearer resource_metadata="{resource_metadata_url(request)}"'}
        raise


@router.post("/mcp")
async def mcp(request: Request, who: Caller = Depends(mcp_caller)) -> Response:
    try:
        body = json.loads(await request.body())
    except ValueError:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
    # The client is built lazily so initialize and tools/list work without ESPN settings.
    factory = rest.get_client
    # ESPN calls block, so run them off the event loop like FastAPI does for sync routes.
    if isinstance(body, list):  # a batch (2025-03-26 and earlier)
        replies = [r for m in body if (r := await run_in_threadpool(_handle, m, factory, who)) is not None]
        return JSONResponse(replies) if replies else Response(status_code=202)
    reply = await run_in_threadpool(_handle, body, factory, who)
    return JSONResponse(reply) if reply is not None else Response(status_code=202)


@router.get("/mcp")
@router.delete("/mcp")
def mcp_no_stream() -> Response:
    # No server-initiated stream and no sessions to end.
    return Response(status_code=405, headers={"Allow": "POST"})
