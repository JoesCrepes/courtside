"""HTTP client for ESPN's (undocumented) fantasy basketball API."""

from __future__ import annotations

import json
from typing import Any

import requests

from .config import Config
from .models import Player, Team
from .slots import SLOT_IDS
from .transactions import (
    LineupMove,
    free_agent_payload,
    lineup_payload,
    plan_move,
    slot_counts_from_settings,
    waiver_payload,
)

READS = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba"
WRITES = "https://lm-api-writes.fantasy.espn.com/apis/v3/games/fba"


class EspnError(RuntimeError):
    pass


class EspnWriteError(EspnError):
    def __init__(self, status: int, body: Any):
        self.status = status
        self.body = body
        super().__init__(f"ESPN rejected the transaction (HTTP {status}): {_messages(body)}")


def _messages(body: Any) -> str:
    """Pull human-readable messages out of an ESPN error body if present."""
    if isinstance(body, dict):
        msgs = body.get("messages") or body.get("details") or []
        if isinstance(msgs, list) and msgs:
            return "; ".join(
                m.get("message", str(m)) if isinstance(m, dict) else str(m) for m in msgs
            )
    return str(body)[:500]


class EspnClient:
    def __init__(self, config: Config, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if config.espn_s2 and config.swid:
            self.session.cookies.set("espn_s2", config.espn_s2, domain=".espn.com")
            self.session.cookies.set("SWID", config.swid, domain=".espn.com")

    # ---- URLs -----------------------------------------------------------

    def _league_path(self) -> str:
        c = self.config
        return f"/seasons/{c.season}/segments/0/leagues/{c.league_id}"

    @property
    def reads_url(self) -> str:
        return READS + self._league_path()

    @property
    def writes_url(self) -> str:
        return WRITES + self._league_path() + "/transactions/"

    # ---- reads ----------------------------------------------------------

    def _get(self, params: list[tuple[str, Any]], headers: dict[str, str] | None = None) -> dict:
        r = self.session.get(self.reads_url, params=params, headers=headers, timeout=20)
        if r.status_code in (401, 403):
            raise EspnError(
                f"HTTP {r.status_code}: private league needs valid ESPN_S2 and ESPN_SWID cookies"
            )
        if r.status_code == 404:
            raise EspnError(f"league {self.config.league_id} not found for season {self.config.season}")
        r.raise_for_status()
        return r.json()

    def league(self, *views: str, scoring_period: int | None = None) -> dict:
        params: list[tuple[str, Any]] = [("view", v) for v in views]
        if scoring_period is not None:
            params.append(("scoringPeriodId", scoring_period))
        return self._get(params)

    def current_scoring_period(self) -> int:
        """Today's scoring period. In basketball, one scoring period = one day."""
        data = self.league("mStatus")
        return int(data.get("scoringPeriodId") or data["status"]["latestScoringPeriod"])

    def settings(self) -> dict:
        return self.league("mSettings")["settings"]

    def teams(self, scoring_period: int | None = None) -> list[Team]:
        data = self.league("mTeam", "mRoster", scoring_period=scoring_period)
        return [Team.from_json(t) for t in data.get("teams", [])]

    def team(self, team_id: int | None = None, scoring_period: int | None = None) -> Team:
        team_id = team_id or self._my_team_id()
        for t in self.teams(scoring_period):
            if t.id == team_id:
                return t
        raise EspnError(f"team {team_id} not found in league {self.config.league_id}")

    def free_agents(self, limit: int = 25, position: str | None = None) -> list[Player]:
        filt: dict[str, Any] = {
            "players": {
                "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
                "limit": limit,
                "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
            }
        }
        if position:
            filt["players"]["filterSlotIds"] = {"value": [SLOT_IDS[position.upper()]]}
        data = self._get([("view", "kona_player_info")], headers={"x-fantasy-filter": json.dumps(filt)})
        return [Player.from_pool_entry(e) for e in data.get("players", [])]

    def _my_team_id(self) -> int:
        if self.config.team_id is None:
            raise EspnError("ESPN_TEAM_ID is not set")
        return self.config.team_id

    def _member_id(self) -> str:
        if not self.config.swid:
            raise EspnError("ESPN_SWID is required for writes")
        return self.config.swid

    # ---- writes ---------------------------------------------------------

    def submit(self, payload: dict, *, execute: bool = False) -> dict:
        """POST a transaction. Dry-run unless execute=True AND writes are enabled.

        Returns {"dry_run": True, "url": ..., "payload": ...} for dry runs, or
        ESPN's JSON response when executed.
        """
        if not execute or not self.config.write_enabled:
            return {
                "dry_run": True,
                "reason": "pass --execute" if not execute else "set ESPN_WRITE_ENABLED=1",
                "url": self.writes_url,
                "payload": payload,
            }
        if not (self.config.espn_s2 and self.config.swid):
            raise EspnError("writes need ESPN_S2 and ESPN_SWID")
        r = self.session.post(self.writes_url, json=payload, timeout=20)
        try:
            body: Any = r.json()
        except ValueError:
            body = r.text
        if not r.ok:
            raise EspnWriteError(r.status_code, body)
        return body

    def move(
        self, player_query: str, to_slot: int, *, swap_with: str | None = None,
        scoring_period: int | None = None, execute: bool = False,
    ) -> dict:
        period = scoring_period or self.current_scoring_period()
        team = self.team(scoring_period=period)
        player = team.find(player_query)
        other = team.find(swap_with).id if swap_with else None
        moves = plan_move(team, player.id, to_slot, slot_counts_from_settings(self.settings()), other)
        return self.submit(self.build_lineup(moves, period), execute=execute)

    def build_lineup(self, moves: list[LineupMove], scoring_period: int) -> dict:
        return lineup_payload(self._my_team_id(), self._member_id(), scoring_period, moves)

    def add_drop(
        self, add_id: int | None, drop_id: int | None, *, waiver: bool = False,
        bid: int | None = None, execute: bool = False,
    ) -> dict:
        period = self.current_scoring_period()
        if waiver:
            if add_id is None:
                raise ValueError("a waiver claim needs a player to add")
            payload = waiver_payload(self._my_team_id(), self._member_id(), period, add_id, drop_id, bid)
        else:
            payload = free_agent_payload(self._my_team_id(), self._member_id(), period, add_id, drop_id)
        return self.submit(payload, execute=execute)
