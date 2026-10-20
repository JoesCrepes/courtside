"""HTTP API over courtside, for the Android app. Deployed on Vercel (see api/index.py).

Every route except /health needs COURTSIDE_API_KEY, sent as
`Authorization: Bearer <key>` or `?key=<key>`. If the key isn't configured,
those routes refuse everything. This stands in until Supabase Auth is wired up.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException, Request

from courtside import Config, EspnClient, EspnError
from courtside.models import Player, Team

app = FastAPI(title="courtside", docs_url=None, redoc_url=None)


def require_key(request: Request) -> None:
    expected = os.environ.get("COURTSIDE_API_KEY")
    if not expected:
        raise HTTPException(503, "COURTSIDE_API_KEY is not configured")
    auth = request.headers.get("authorization", "")
    given = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else request.query_params.get("key", "")
    if not secrets.compare_digest(given, expected):
        raise HTTPException(401, "bad or missing API key")


def get_client() -> EspnClient:
    try:
        return EspnClient(Config.from_env(dotenv=None))
    except SystemExit as e:  # Config.from_env exits when the league id is missing
        raise HTTPException(500, str(e)) from None


def _player(p: Player) -> dict:
    return {**asdict(p), "slot": p.slot, "is_starting": p.is_starting}


def _team(t: Team) -> dict:
    return {"id": t.id, "name": t.name, "abbrev": t.abbrev, "roster": [_player(p) for p in t.roster]}


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/roster", dependencies=[Depends(require_key)])
def roster(day: int | None = None, team: int | None = None, client: EspnClient = Depends(get_client)) -> dict:
    try:
        return _team(client.team(team, scoring_period=day))
    except EspnError as e:
        # 502: the problem is upstream (ESPN or our cookies), not the request.
        raise HTTPException(502, str(e)) from None
