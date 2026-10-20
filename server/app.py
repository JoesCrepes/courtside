"""HTTP API over courtside, for the Android app. Deployed on Vercel (see api/index.py).

Auth is in server/auth.py: reads take a Supabase user or COURTSIDE_API_KEY,
writes take a Supabase user only.

Every write is two calls. POST .../preview returns what would happen plus
`expect` (the transaction items). POST .../confirm takes the same intent and
`expect`, re-plans against fresh ESPN data, and only submits if the plan is
unchanged; otherwise it answers 409 with the new preview.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from courtside import Config, EspnClient, EspnError, EspnWriteError
from courtside.models import Matchup, Player, ProSchedule, Team
from courtside.slots import POSITIONS, slot_id, slot_name
from courtside.transactions import LineupError

from .auth import Caller, caller, writer

app = FastAPI(title="courtside", docs_url=None, redoc_url=None)


# ---- errors ----------------------------------------------------------------

@app.exception_handler(EspnWriteError)
def _espn_write_error(request: Request, e: EspnWriteError) -> JSONResponse:
    # ESPN understood us and said no (locked player, full roster, ...).
    return JSONResponse({"detail": str(e), "espn": e.body}, status_code=422)


@app.exception_handler(EspnError)
def _espn_error(request: Request, e: EspnError) -> JSONResponse:
    # 502: the problem is upstream (ESPN or our cookies), not the request.
    return JSONResponse({"detail": str(e)}, status_code=502)


@app.exception_handler(LineupError)
@app.exception_handler(KeyError)
@app.exception_handler(ValueError)
def _bad_request(request: Request, e: Exception) -> JSONResponse:
    msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
    return JSONResponse({"detail": msg}, status_code=400)


# ---- plumbing --------------------------------------------------------------

def get_client() -> EspnClient:
    try:
        return EspnClient(Config.from_env(dotenv=None))
    except SystemExit as e:  # Config.from_env exits when the league id is missing
        raise HTTPException(500, str(e)) from None


def _game(p: Player, sched: ProSchedule, day: int) -> dict | None:
    g = sched.game_for(p.pro_team_id, day)
    if g is None:
        return None
    home = g.home_pro_team_id == p.pro_team_id
    opp = g.away_pro_team_id if home else g.home_pro_team_id
    return {"id": g.id, "start": g.date, "home": home, "opponent": sched.teams.get(opp, str(opp))}


def _player(p: Player, sched: ProSchedule, day: int) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "pro_team": sched.teams.get(p.pro_team_id) if p.pro_team_id else None,
        "positions": [slot_name(s) for s in p.eligible_slots if s in POSITIONS],
        "eligible_slots": [slot_name(s) for s in p.eligible_slots],
        "slot": p.slot if p.lineup_slot >= 0 else None,
        "is_starting": p.is_starting if p.lineup_slot >= 0 else False,
        "injury_status": p.injury_status,
        "status": p.status,
        "on_team_id": p.on_team_id,
        "percent_owned": p.percent_owned,
        "lineup_locked": p.lineup_locked,
        "stats": p.stats,
        "game": _game(p, sched, day),
    }


def _team_summary(t: Team) -> dict:
    return {
        "id": t.id, "name": t.name, "abbrev": t.abbrev, "logo": t.logo,
        "wins": t.wins, "losses": t.losses, "ties": t.ties,
        "points_for": t.points_for, "points_against": t.points_against,
        "playoff_seed": t.playoff_seed, "waiver_rank": t.waiver_rank,
    }


def _matchup(m: Matchup, names: dict[int, str]) -> dict:
    def side(team_id: int | None, points: float) -> dict | None:
        return None if team_id is None else {"team_id": team_id, "name": names.get(team_id), "points": points}

    return {
        "id": m.id, "week": m.week, "playoff": m.playoff, "winner": m.winner,
        "home": side(m.home_team_id, m.home_points), "away": side(m.away_team_id, m.away_points),
    }


# ---- reads -----------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/context")
def context(who: Caller = Depends(caller), client: EspnClient = Depends(get_client)) -> dict:
    c = client.config
    return {
        **client.status(),
        "league_id": c.league_id, "season": c.season, "team_id": c.team_id,
        "writes_enabled": c.write_enabled, "caller": who.kind, "email": who.email,
    }


@app.get("/league", dependencies=[Depends(caller)])
def league(client: EspnClient = Depends(get_client)) -> dict:
    s = client.settings()
    roster, scoring, acq = s["rosterSettings"], s.get("scoringSettings", {}), s.get("acquisitionSettings", {})
    return {
        "name": s.get("name"),
        "scoring_type": scoring.get("scoringType"),
        "scoring": [{"stat_id": i["statId"], "points": i["points"]} for i in scoring.get("scoringItems", [])],
        "slots": {slot_name(int(k)): v for k, v in roster["lineupSlotCounts"].items() if v},
        "acquisitions": {
            "type": acq.get("acquisitionType"),
            "per_week": acq.get("matchupAcquisitionLimit"),
            "budget": acq.get("acquisitionBudget") if acq.get("isUsingAcquisitionBudget") else None,
            "waiver_hours": acq.get("waiverHours"),
        },
        "standings": [_team_summary(t) for t in client.standings()],
    }


def _roster(client: EspnClient, team_id: int | None, day: int | None) -> dict:
    day = day or client.current_scoring_period()
    team = client.team(team_id, scoring_period=day)
    sched = client.pro_schedule()
    return {**_team_summary(team), "day": day, "roster": [_player(p, sched, day) for p in team.roster]}


@app.get("/roster", dependencies=[Depends(caller)])
def my_roster(day: int | None = None, client: EspnClient = Depends(get_client)) -> dict:
    return _roster(client, None, day)


@app.get("/teams/{team_id}", dependencies=[Depends(caller)])
def team_roster(team_id: int, day: int | None = None, client: EspnClient = Depends(get_client)) -> dict:
    return _roster(client, team_id, day)


@app.get("/scoreboard", dependencies=[Depends(caller)])
def scoreboard(week: int | None = None, client: EspnClient = Depends(get_client)) -> dict:
    week = week or client.status()["matchup_period"]
    names = {t.id: t.name for t in client.standings()}
    return {"week": week, "matchups": [_matchup(m, names) for m in client.scoreboard(week)]}


@app.get("/players", dependencies=[Depends(caller)])
def players(
    q: str | None = None, pos: str | None = None, available: bool = True,
    limit: int = 25, offset: int = 0, day: int | None = None,
    client: EspnClient = Depends(get_client),
) -> dict:
    day = day or client.current_scoring_period()
    found = client.players(query=q, position=pos, available=available, limit=min(limit, 100), offset=offset)
    sched = client.pro_schedule()
    return {"day": day, "players": [_player(p, sched, day) for p in found]}


@app.get("/activity", dependencies=[Depends(caller)])
def activity(limit: int = 25, client: EspnClient = Depends(get_client)) -> dict:
    names = client.player_names()
    return {"activity": [
        {"date": a.date, "items": [
            {"kind": i.kind, "player_id": i.player_id, "player": names.get(i.player_id), "team_id": i.team_id,
             "from_slot": slot_name(i.from_slot) if i.from_slot is not None else None,
             "to_slot": slot_name(i.to_slot) if i.to_slot is not None else None}
            for i in a.items
        ]}
        for a in client.activity(min(limit, 50))
    ]}


@app.get("/pending", dependencies=[Depends(caller)])
def pending(client: EspnClient = Depends(get_client)) -> dict:
    names = client.player_names()
    return {"pending": [
        {"id": t.get("id"), "type": t.get("type"), "status": t.get("status"), "team_id": t.get("teamId"),
         "bid": t.get("bidAmount"), "expires": t.get("expirationDate"),
         "items": [{"type": i.get("type"), "player_id": i.get("playerId"), "player": names.get(i.get("playerId")),
                    "from_team_id": i.get("fromTeamId"), "to_team_id": i.get("toTeamId")}
                   for i in t.get("items", [])]}
        for t in client.pending()
    ]}


# ---- writes (preview -> confirm) -------------------------------------------

class LineupIntent(BaseModel):
    player: str  # id or name fragment
    slot: str  # "PG", "UTIL", "BE", ... or numeric id
    swap_with: str | None = None
    day: int | None = None


class RosterIntent(BaseModel):
    add: int | None = None  # player id
    drop: str | None = None  # rostered player id or name fragment
    waiver: bool = False
    bid: int | None = None


class Expect(BaseModel):
    expect: list[dict[str, Any]]
    scoring_period: int


class LineupConfirm(LineupIntent, Expect):
    pass


class RosterConfirm(RosterIntent, Expect):
    pass


def _preview(client: EspnClient, payload: dict) -> dict:
    names = client.player_names()
    summary = []
    for i in payload["items"]:
        who = names.get(i["playerId"], str(i["playerId"]))
        if i["type"] == "LINEUP":
            summary.append(f"{who}: {slot_name(i['fromLineupSlotId'])} -> {slot_name(i['toLineupSlotId'])}")
        elif i["type"] == "ADD":
            bid = payload.get("bidAmount")
            claim = payload["type"] == "WAIVER"
            summary.append(f"{'Claim' if claim else 'Add'} {who}" + (f" (bid ${bid})" if claim and bid else ""))
        else:
            summary.append(f"Drop {who}")
    # memberId is the SWID cookie; the app doesn't need it.
    return {
        "type": payload["type"], "summary": summary,
        "scoring_period": payload["scoringPeriodId"], "expect": payload["items"],
    }


def _plan_lineup(client: EspnClient, body: LineupIntent) -> dict:
    return client.plan_lineup(body.player, slot_id(body.slot), swap_with=body.swap_with, scoring_period=body.day)


def _plan_roster(client: EspnClient, body: RosterIntent) -> dict:
    drop_id = client.team().find(body.drop).id if body.drop else None
    return client.plan_add_drop(body.add, drop_id, waiver=body.waiver, bid=body.bid)


def _confirm(client: EspnClient, payload: dict, body: Expect) -> dict:
    if payload["items"] != body.expect or payload["scoringPeriodId"] != body.scoring_period:
        raise HTTPException(409, {"message": "the plan changed since the preview", "preview": _preview(client, payload)})
    result = client.submit(payload, execute=True)
    if result.get("dry_run"):
        raise HTTPException(503, "writes are disabled on the server (ESPN_WRITE_ENABLED)")
    return {"status": result.get("status"), "id": result.get("id"), **_preview(client, payload)}


@app.post("/lineup/preview", dependencies=[Depends(caller)])
def lineup_preview(body: LineupIntent, client: EspnClient = Depends(get_client)) -> dict:
    return _preview(client, _plan_lineup(client, body))


@app.post("/lineup/confirm", dependencies=[Depends(writer)])
def lineup_confirm(body: LineupConfirm, client: EspnClient = Depends(get_client)) -> dict:
    return _confirm(client, _plan_lineup(client, body), body)


@app.post("/roster/preview", dependencies=[Depends(caller)])
def roster_preview(body: RosterIntent, client: EspnClient = Depends(get_client)) -> dict:
    return _preview(client, _plan_roster(client, body))


@app.post("/roster/confirm", dependencies=[Depends(writer)])
def roster_confirm(body: RosterConfirm, client: EspnClient = Depends(get_client)) -> dict:
    return _confirm(client, _plan_roster(client, body), body)
