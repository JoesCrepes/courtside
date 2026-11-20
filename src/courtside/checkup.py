"""Lineup and roster checks: what needs attention today and this week.

Everything here is pure. It takes a team, the NBA schedule and the league's
slot counts, and returns findings; the caller fetches the data.

The core is `best_starters`, which picks who should start on a given day:
as many players with a game as the slots allow, preferring the higher
fantasy average. Assigning players to slots is a bipartite matching; adding
players in order of value and keeping each one that still fits (re-routing
earlier picks if needed) gives the best set, because the sets of players
that can all start together form a matroid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Player, ProSchedule, Team
from .slots import BENCH, IR, IR_ELIGIBLE, slot_name

# Injury statuses that mean the player won't play today.
CANT_PLAY = {"OUT", "INJURY_RESERVE", "SUSPENSION"}
# Statuses worth checking again before lineups lock.
UNCERTAIN = {"DAY_TO_DAY", "QUESTIONABLE", "DOUBTFUL", "GAME_TIME_DECISION"}

# Splits to rank players by, most relevant first (see models.parse_stats).
_VALUE_SPLITS = ("last15", "season", "last30", "projected", "prev_season")


def value(p: Player) -> float:
    """A player's fantasy points per game, from the most relevant split we have."""
    for split in _VALUE_SPLITS:
        s = p.stats.get(split)
        if s and s.get("gp"):
            return float(s.get("avg", 0.0))
    return 0.0


def starting_slots(slot_counts: dict[int, int]) -> list[int]:
    """One entry per starting slot, e.g. [PG, SG, ..., UTIL, UTIL, UTIL]."""
    return [sid for sid, n in sorted(slot_counts.items()) if sid not in (BENCH, IR) for _ in range(n)]


def best_starters(
    roster: list[Player], slot_counts: dict[int, int], has_game: set[int], *, respect_locks: bool = True,
) -> dict[int, int]:
    """Best lineup for a day, as player id -> slot id.

    Only healthy players with a game and not in IR are candidates. With
    `respect_locks`, players whose game has started stay where they are: a
    locked starter keeps their slot and a locked bench player can't start.
    """
    slots = starting_slots(slot_counts)
    owner: list[int | None] = [None] * len(slots)  # slot index -> player id
    by_id = {p.id: p for p in roster}

    if respect_locks:
        for p in roster:
            if p.lineup_locked and p.is_starting and p.lineup_slot in slots:
                i = next((i for i, s in enumerate(slots) if s == p.lineup_slot and owner[i] is None), None)
                if i is not None:
                    owner[i] = p.id

    def fits(pid: int, seen: set[int]) -> bool:
        for i, sid in enumerate(slots):
            if sid not in by_id[pid].eligible_slots or i in seen:
                continue
            seen.add(i)
            cur = owner[i]
            if cur is None or (not (respect_locks and by_id[cur].lineup_locked) and fits(cur, seen)):
                owner[i] = pid
                return True
        return False

    placed = set(o for o in owner if o is not None)
    candidates = [
        p for p in roster
        if p.id not in placed and p.id in has_game and p.lineup_slot != IR
        and p.injury_status not in CANT_PLAY and not (respect_locks and p.lineup_locked)
    ]
    for p in sorted(candidates, key=value, reverse=True):
        fits(p.id, set())
    return {pid: slots[i] for i, pid in enumerate(owner) if pid is not None}


def games_on(day: int, roster: list[Player], sched: ProSchedule) -> set[int]:
    return {p.id for p in roster if sched.game_for(p.pro_team_id, day)}


@dataclass
class Finding:
    severity: str  # "action", "warning" or "info"
    kind: str
    message: str
    players: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {"severity": self.severity, "kind": self.kind, "message": self.message, "players": self.players}


def _opp(p: Player, sched: ProSchedule, day: int) -> str:
    g = sched.game_for(p.pro_team_id, day)
    if g is None:
        return ""
    other = g.away_pro_team_id if g.home_pro_team_id == p.pro_team_id else g.home_pro_team_id
    return f" ({'vs' if g.home_pro_team_id == p.pro_team_id else '@'} {sched.teams.get(other, other)})"


def check_day(team: Team, sched: ProSchedule, day: int, slot_counts: dict[int, int]) -> list[Finding]:
    """Problems with a team's lineup on one day, most urgent first."""
    out: list[Finding] = []
    roster = team.roster
    playing = games_on(day, roster, sched)
    starters = [p for p in roster if p.is_starting]

    # Lineup: compare who starts with who could.
    best = best_starters(roster, slot_counts, playing)
    active_now = [p for p in starters if p.id in playing and p.injury_status not in CANT_PLAY]
    start = sorted((p for p in roster if p.id in best and not p.is_starting), key=value, reverse=True)
    sit = sorted((p for p in starters if p.id not in best and not p.lineup_locked), key=value)
    gained = len(best) - len(active_now)
    if gained > 0:
        out.append(Finding(
            "action", "lineup",
            f"You can start {gained} more player{'s' if gained != 1 else ''} with games today. "
            f"Start {', '.join(p.name + _opp(p, sched, day) for p in start)}"
            + (f"; sit {', '.join(p.name for p in sit)}." if sit else "."),
            [p.name for p in start + sit],
        ))
    elif start:
        out.append(Finding(
            "info", "lineup",
            f"Same number of games either way, but {', '.join(f'{p.name} ({value(p):.1f})' for p in start)} "
            f"average{'s' if len(start) == 1 else ''} more than "
            f"{', '.join(f'{p.name} ({value(p):.1f})' for p in sit)}.",
            [p.name for p in start + sit],
        ))

    for p in starters:
        if p.lineup_locked:
            continue
        if p.injury_status in CANT_PLAY:
            out.append(Finding("action", "injured_starter", f"{p.name} is starting but is {p.injury_status}.", [p.name]))
        elif p.id not in playing:
            out.append(Finding("warning", "no_game", f"{p.name} is starting but has no game today.", [p.name]))
        elif p.injury_status in UNCERTAIN:
            out.append(Finding(
                "warning", "uncertain_starter",
                f"{p.name} is {p.injury_status}; check again before tip-off{_opp(p, sched, day)}.", [p.name]))

    open_slots = len(starting_slots(slot_counts)) - len(starters)
    if open_slots > 0:
        out.append(Finding("action", "empty_slot", f"{open_slots} starting slot(s) are empty."))

    # IR: a healthy player in IR makes the roster illegal, and an empty IR
    # slot is a free bench spot for anyone who's out.
    on_ir = [p for p in roster if p.lineup_slot == IR]
    for p in on_ir:
        if p.injury_status not in IR_ELIGIBLE:
            out.append(Finding(
                "action", "ir_healthy",
                f"{p.name} is in IR but is now {p.injury_status}. ESPN can block roster moves until they're activated.",
                [p.name]))
    if len(on_ir) < slot_counts.get(IR, 0):
        for p in roster:
            if p.lineup_slot != IR and p.injury_status in IR_ELIGIBLE and IR in p.eligible_slots:
                out.append(Finding(
                    "info", "ir_open", f"{p.name} is {p.injury_status} and could go to IR to free a roster spot.",
                    [p.name]))

    rank = {"action": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda f: rank[f.severity])


def games_left(
    team: Team, sched: ProSchedule, days: list[int], slot_counts: dict[int, int], today: int,
) -> int:
    """Most starts a team can still get across `days`, from its current roster."""
    total = 0
    for day in days:
        playing = games_on(day, team.roster, sched)
        # Locks only apply today; later days start fresh.
        total += len(best_starters(team.roster, slot_counts, playing, respect_locks=day == today))
    return total


def remaining_days(settings: dict[str, Any], matchup_period: int, today: int) -> list[int]:
    """Scoring periods left in a matchup period, including today."""
    periods = (settings.get("scheduleSettings") or {}).get("matchupPeriods") or {}
    return sorted(d for d in periods.get(str(matchup_period), []) if d >= today)
