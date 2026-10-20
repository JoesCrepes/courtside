"""Thin typed views over ESPN's league JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .slots import NON_STARTING, slot_name

# (statSourceId, statSplitTypeId) -> our name. Source 0 is actual, 1 projected;
# split 0 is the whole season, 1/2/3 the last 7/15/30 days.
_STAT_SPLITS = {
    (0, 0): "season",
    (0, 1): "last7",
    (0, 2): "last15",
    (0, 3): "last30",
    (1, 0): "projected",
}
GAMES_PLAYED = "42"  # ESPN stat id


def parse_stats(raw: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Fantasy point totals/averages per split, for the newest season present.

    The previous season's actuals come back as "prev_season".
    """
    if not raw:
        return {}
    season = max(s.get("seasonId", 0) for s in raw)
    out: dict[str, dict[str, float]] = {}
    for s in raw:
        if s.get("scoringPeriodId", 0) != 0:
            continue  # per-day lines; we only want aggregates
        key = (s.get("statSourceId"), s.get("statSplitTypeId"))
        name = _STAT_SPLITS.get(key) if s.get("seasonId") == season else (
            "prev_season" if key == (0, 0) and s.get("seasonId") == season - 1 else None
        )
        if name:
            out[name] = {
                "total": s.get("appliedTotal", 0.0),
                "avg": s.get("appliedAverage", 0.0),
                "gp": (s.get("stats") or {}).get(GAMES_PLAYED, 0),
            }
    return out


@dataclass
class Player:
    id: int
    name: str
    lineup_slot: int
    eligible_slots: list[int]
    injury_status: str = "ACTIVE"
    pro_team_id: int | None = None
    percent_owned: float | None = None
    # Pool status: "FREEAGENT", "WAIVERS" or "ONTEAM".
    status: str | None = None
    on_team_id: int | None = None
    lineup_locked: bool = False
    stats: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def is_starting(self) -> bool:
        return self.lineup_slot not in NON_STARTING

    @property
    def slot(self) -> str:
        return slot_name(self.lineup_slot)

    @classmethod
    def from_roster_entry(cls, entry: dict[str, Any]) -> "Player":
        pool = entry["playerPoolEntry"]
        p = pool["player"]
        return cls(
            id=entry["playerId"],
            name=p.get("fullName", str(entry["playerId"])),
            lineup_slot=entry["lineupSlotId"],
            eligible_slots=list(p.get("eligibleSlots", [])),
            injury_status=p.get("injuryStatus") or "ACTIVE",
            pro_team_id=p.get("proTeamId"),
            percent_owned=(p.get("ownership") or {}).get("percentOwned"),
            status="ONTEAM",
            on_team_id=pool.get("onTeamId"),
            lineup_locked=bool(pool.get("lineupLocked")),
            stats=parse_stats(p.get("stats", [])),
        )

    @classmethod
    def from_pool_entry(cls, entry: dict[str, Any]) -> "Player":
        """A player from the kona_player_info (free agent) view."""
        p = entry["player"]
        return cls(
            id=entry["id"],
            name=p.get("fullName", str(entry["id"])),
            lineup_slot=-1,
            eligible_slots=list(p.get("eligibleSlots", [])),
            injury_status=p.get("injuryStatus") or "ACTIVE",
            pro_team_id=p.get("proTeamId"),
            percent_owned=(p.get("ownership") or {}).get("percentOwned"),
            status=entry.get("status"),
            on_team_id=entry.get("onTeamId") or None,
            lineup_locked=bool(entry.get("lineupLocked")),
            stats=parse_stats(p.get("stats", [])),
        )


@dataclass
class Team:
    id: int
    name: str
    abbrev: str = ""
    roster: list[Player] = field(default_factory=list)
    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: float = 0.0
    points_against: float = 0.0
    playoff_seed: int | None = None
    waiver_rank: int | None = None
    logo: str | None = None

    @classmethod
    def from_json(cls, t: dict[str, Any]) -> "Team":
        # ESPN has used both "name" and "location"+"nickname" over the years.
        name = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
        entries = (t.get("roster") or {}).get("entries", [])
        overall = (t.get("record") or {}).get("overall", {})
        return cls(
            id=t["id"],
            name=name or f"Team {t['id']}",
            abbrev=t.get("abbrev", ""),
            roster=[Player.from_roster_entry(e) for e in entries],
            wins=overall.get("wins", 0),
            losses=overall.get("losses", 0),
            ties=overall.get("ties", 0),
            points_for=overall.get("pointsFor", 0.0),
            points_against=overall.get("pointsAgainst", 0.0),
            playoff_seed=t.get("playoffSeed"),
            waiver_rank=t.get("waiverRank"),
            logo=t.get("logo"),
        )

    def player(self, player_id: int) -> Player:
        for p in self.roster:
            if p.id == player_id:
                return p
        raise KeyError(f"player {player_id} is not on {self.name}'s roster")

    def find(self, query: str) -> Player:
        """Find a rostered player by id or (case-insensitive) name fragment."""
        if query.isdigit():
            return self.player(int(query))
        matches = [p for p in self.roster if query.lower() in p.name.lower()]
        if len(matches) != 1:
            names = ", ".join(p.name for p in matches) or "none"
            raise KeyError(f"{query!r} matched {len(matches)} rostered players: {names}")
        return matches[0]


@dataclass
class Matchup:
    id: int
    week: int
    home_team_id: int | None
    away_team_id: int | None
    home_points: float
    away_points: float
    # "HOME", "AWAY", "TIE" or "UNDECIDED".
    winner: str
    playoff: bool

    @classmethod
    def from_json(cls, m: dict[str, Any]) -> "Matchup":
        home, away = m.get("home") or {}, m.get("away") or {}

        def pts(side: dict[str, Any]) -> float:
            # Live totals include games in progress; fall back to final.
            return side.get("totalPointsLive", side.get("totalPoints", 0.0))

        return cls(
            id=m["id"],
            week=m["matchupPeriodId"],
            home_team_id=home.get("teamId"),
            away_team_id=away.get("teamId"),  # None on a bye
            home_points=pts(home),
            away_points=pts(away),
            winner=m.get("winner", "UNDECIDED"),
            playoff=m.get("playoffTierType", "NONE") != "NONE",
        )


@dataclass
class ProGame:
    id: int
    scoring_period: int
    date: int  # epoch milliseconds
    home_pro_team_id: int
    away_pro_team_id: int


@dataclass
class ProSchedule:
    """NBA teams and their games, keyed by fantasy scoring period (day)."""

    teams: dict[int, str]  # pro team id -> abbrev
    games: dict[int, dict[int, ProGame]]  # scoring period -> pro team id -> game

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ProSchedule":
        teams: dict[int, str] = {}
        games: dict[int, dict[int, ProGame]] = {}
        for t in data["settings"]["proTeams"]:
            teams[t["id"]] = t.get("abbrev", "").upper()
            for period, day_games in (t.get("proGamesByScoringPeriod") or {}).items():
                for g in day_games:
                    game = ProGame(
                        id=g["id"], scoring_period=int(period), date=g["date"],
                        home_pro_team_id=g["homeProTeamId"], away_pro_team_id=g["awayProTeamId"],
                    )
                    games.setdefault(int(period), {})[t["id"]] = game
        return cls(teams=teams, games=games)

    def game_for(self, pro_team_id: int | None, scoring_period: int) -> ProGame | None:
        return self.games.get(scoring_period, {}).get(pro_team_id) if pro_team_id else None


# kona_league_communication messageTypeIds we know how to label.
ACTIVITY_TYPES = {
    178: "ADD",  # free agent
    179: "DROP",
    180: "ADD",  # off waivers
    181: "DROP",
    188: "MOVE",  # lineup slot change
    239: "DROP",
    244: "TRADE",
}


@dataclass
class ActivityItem:
    kind: str
    player_id: int
    team_id: int | None
    from_slot: int | None = None
    to_slot: int | None = None


@dataclass
class Activity:
    date: int  # epoch milliseconds
    items: list[ActivityItem]

    @classmethod
    def from_topic(cls, topic: dict[str, Any]) -> "Activity":
        items = []
        for m in topic.get("messages", []):
            kind = ACTIVITY_TYPES.get(m.get("messageTypeId"), str(m.get("messageTypeId")))
            if kind == "MOVE":
                # For lineup moves "from"/"to" are slot ids and "for" is the team.
                items.append(ActivityItem(kind, m["targetId"], m.get("for"), m.get("from"), m.get("to")))
            else:
                # For adds and drops, "to" is the team (even for a drop).
                items.append(ActivityItem(kind, m["targetId"], m.get("to") or m.get("from")))
        return cls(date=topic.get("date", 0), items=items)
