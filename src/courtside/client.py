"""HTTP client for ESPN's (undocumented) fantasy basketball API."""

from __future__ import annotations

import json
import time
from typing import Any

import requests

from .config import Config
from .models import Activity, Matchup, Player, ProSchedule, Team
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


# Season-static data (NBA schedule, player names), shared across requests in
# one process: (season, kind) -> (fetched_at, value).
_CACHE: dict[tuple[int, str], tuple[float, Any]] = {}
CACHE_TTL = 6 * 3600


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

    @property
    def game_url(self) -> str:
        return READS + f"/seasons/{self.config.season}"

    def _get(
        self, params: list[tuple[str, Any]], headers: dict[str, str] | None = None, url: str | None = None
    ) -> Any:
        r = self.session.get(url or self.reads_url, params=params, headers=headers, timeout=20)
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

    def status(self) -> dict[str, int]:
        """Today's scoring period (one per day) and matchup period (week)."""
        data = self.league("mStatus")
        st = data.get("status", {})
        return {
            "scoring_period": int(data.get("scoringPeriodId") or st["latestScoringPeriod"]),
            "matchup_period": int(st.get("currentMatchupPeriod") or 1),
        }

    def current_scoring_period(self) -> int:
        return self.status()["scoring_period"]

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
        return self.players(limit=limit, position=position)

    def players(
        self, *, query: str | None = None, position: str | None = None, available: bool = True,
        limit: int = 25, offset: int = 0,
    ) -> list[Player]:
        """Players from the league's pool, most-owned first.

        available=True limits to free agents and waivers; False includes
        rostered players. `query` matches names (ESPN's filterName).
        """
        players: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
        }
        if available:
            players["filterStatus"] = {"value": ["FREEAGENT", "WAIVERS"]}
        else:
            players["filterActive"] = {"value": True}
        if query:
            # filterName needs filterActive; ESPN answers 400 without it.
            players["filterName"] = {"value": query}
            players["filterActive"] = {"value": True}
        if position:
            players["filterSlotIds"] = {"value": [SLOT_IDS[position.upper()]]}
        data = self._get(
            [("view", "kona_player_info")], headers={"x-fantasy-filter": json.dumps({"players": players})}
        )
        return [Player.from_pool_entry(e) for e in data.get("players", [])]

    def standings(self) -> list[Team]:
        data = self.league("mTeam", "mStandings")
        teams = [Team.from_json(t) for t in data.get("teams", [])]
        return sorted(teams, key=lambda t: (t.playoff_seed or 99, -t.points_for))

    def scoreboard(self, week: int | None = None) -> list[Matchup]:
        week = week or self.status()["matchup_period"]
        data = self.league("mMatchupScore", "mScoreboard")
        return [Matchup.from_json(m) for m in data.get("schedule", []) if m.get("matchupPeriodId") == week]

    def _cached(self, kind: str, fetch: Any) -> Any:
        key = (self.config.season, kind)
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
        value = fetch()
        _CACHE[key] = (time.time(), value)
        return value

    def pro_schedule(self) -> ProSchedule:
        return self._cached(
            "pro_schedule",
            lambda: ProSchedule.from_json(self._get([("view", "proTeamSchedules_wl")], url=self.game_url)),
        )

    def player_names(self) -> dict[int, str]:
        """Every active NBA player's name by id (for activity and pending moves)."""
        def fetch() -> dict[int, str]:
            filt = {"filterActive": {"value": True}}
            data = self._get(
                [("view", "players_wl")], headers={"x-fantasy-filter": json.dumps(filt)},
                url=self.game_url + "/players",
            )
            return {p["id"]: p.get("fullName", str(p["id"])) for p in data}
        return self._cached("player_names", fetch)

    def activity(self, limit: int = 25) -> list[Activity]:
        """Recent league transactions, newest first."""
        filt = {"topics": {
            "filterType": {"value": ["ACTIVITY_TRANSACTIONS"]},
            "limit": limit,
            "limitPerMessageSet": {"value": 25},
            "offset": 0,
            "sortMessageDate": {"sortPriority": 1, "sortAsc": False},
            "sortFor": {"sortPriority": 2, "sortAsc": False},
        }}
        data = self._get(
            [("view", "kona_league_communication")], headers={"x-fantasy-filter": json.dumps(filt)},
            url=self.reads_url + "/communication/",
        )
        return [Activity.from_topic(t) for t in data.get("topics", [])]

    def pending(self) -> list[dict]:
        """Pending waiver claims and trades, as ESPN returns them."""
        return self.league("mPendingTransactions").get("pendingTransactions", [])

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

    def plan_lineup(
        self, player_query: str, to_slot: int, *, swap_with: str | None = None,
        scoring_period: int | None = None,
    ) -> dict:
        """The ROSTER payload that would move a player, without sending it."""
        period = scoring_period or self.current_scoring_period()
        team = self.team(scoring_period=period)
        player = team.find(player_query)
        other = team.find(swap_with).id if swap_with else None
        moves = plan_move(team, player.id, to_slot, slot_counts_from_settings(self.settings()), other)
        return self.build_lineup(moves, period)

    def move(
        self, player_query: str, to_slot: int, *, swap_with: str | None = None,
        scoring_period: int | None = None, execute: bool = False,
    ) -> dict:
        payload = self.plan_lineup(player_query, to_slot, swap_with=swap_with, scoring_period=scoring_period)
        return self.submit(payload, execute=execute)

    def build_lineup(self, moves: list[LineupMove], scoring_period: int) -> dict:
        return lineup_payload(self._my_team_id(), self._member_id(), scoring_period, moves)

    def plan_add_drop(
        self, add_id: int | None, drop_id: int | None, *, waiver: bool = False, bid: int | None = None,
    ) -> dict:
        """The FREEAGENT or WAIVER payload for an add/drop, without sending it."""
        period = self.current_scoring_period()
        if waiver:
            if add_id is None:
                raise ValueError("a waiver claim needs a player to add")
            return waiver_payload(self._my_team_id(), self._member_id(), period, add_id, drop_id, bid)
        return free_agent_payload(self._my_team_id(), self._member_id(), period, add_id, drop_id)

    def add_drop(
        self, add_id: int | None, drop_id: int | None, *, waiver: bool = False,
        bid: int | None = None, execute: bool = False,
    ) -> dict:
        return self.submit(self.plan_add_drop(add_id, drop_id, waiver=waiver, bid=bid), execute=execute)
