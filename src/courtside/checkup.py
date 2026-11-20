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

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
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


# ---- the calendar: scoring periods (days), ESPN weeks, matchup periods --------
#
# ESPN numbers each day of the season as a scoring period, starting at 1. Its
# league settings map each matchup period to the ESPN *weeks* it covers
# (scheduleSettings.matchupPeriods, e.g. {"5": [5]}), not to days. ESPN's
# weeks run Monday to Sunday, with week 1 running from day 1 to the first
# Sunday, except the one over the All-Star break (see `long_week`). Nothing in
# the league says which date day 1 is, so we read it off the NBA schedule,
# where every game carries both its day and its date.

# NBA games tip between noon and about 11pm Eastern. A fixed UTC-5 puts every
# one on its Eastern calendar day, with or without daylight saving time.
_EASTERN = timezone(timedelta(hours=-5))


def first_day(sched: ProSchedule) -> date | None:
    """The calendar date of scoring period 1, or None without any games."""
    votes: Counter[date] = Counter()
    for period, games in sched.games.items():
        for g in games.values():
            played = datetime.fromtimestamp(g.date / 1000, _EASTERN).date()
            votes[played - timedelta(days=period - 1)] += 1
    return votes.most_common(1)[0][0] if votes else None


def day_date(start: date, day: int) -> date:
    return start + timedelta(days=day - 1)


def calendar_week_days(start: date, week: int) -> range:
    """The scoring periods in calendar week `week` (Monday to Sunday; week 1 holds day 1)."""
    monday = start - timedelta(days=start.weekday()) + timedelta(weeks=week - 1)
    first = (monday - start).days + 1
    return range(max(first, 1), first + 7)


def calendar_week(start: date, day: int) -> int:
    """The calendar week (as in `calendar_week_days`) that holds scoring period `day`."""
    return (day_date(start, day) - (start - timedelta(days=start.weekday()))).days // 7 + 1


def all_star_break(sched: ProSchedule) -> tuple[int, int] | None:
    """First and last day of the season's longest stretch with no NBA games (3+ days), if any.

    Inside the season that's the All-Star break. Days before the first game and
    after the last don't count.
    """
    played = sorted(d for d, games in sched.games.items() if games)
    best: tuple[int, int] | None = None
    for a, b in zip(played, played[1:]):
        if b - a - 1 >= 3 and (best is None or b - a - 2 > best[1] - best[0]):
            best = (a + 1, b - 1)
    return best


def long_week(sched: ProSchedule, start: date) -> int | None:
    """The calendar week ESPN stretches over the next one too, or None.

    ESPN makes the week the All-Star break starts in and the week it ends in
    one week: in 2026-27 the break runs over Sunday Feb 21, so ESPN's week 18 is
    Feb 15-28 and every later ESPN week is one calendar week later. (That
    league's finalScoringPeriod, 160, is exactly 7 days more than all-7-day
    weeks would give.) A break inside one calendar week stretches nothing.
    """
    gap = all_star_break(sched)
    if gap is None:
        return None
    first, last = (calendar_week(start, d) for d in gap)
    return first if last == first + 1 else None


def week_days(start: date, week: int, stretched: int | None = None) -> range:
    """The scoring periods in ESPN week `week`, given the calendar week ESPN stretches (if any)."""
    if stretched is None or week < stretched:
        return calendar_week_days(start, week)
    if week == stretched:
        return range(calendar_week_days(start, week).start, calendar_week_days(start, week + 1).stop)
    return calendar_week_days(start, week + 1)


def matchup_weeks(settings: dict[str, Any], matchup_period: int) -> list[int]:
    """ESPN weeks in a matchup period; a matchup period is one week if settings don't say."""
    periods = (settings.get("scheduleSettings") or {}).get("matchupPeriods") or {}
    return [int(w) for w in periods.get(str(matchup_period)) or [matchup_period]]


def matchup_days(settings: dict[str, Any], sched: ProSchedule, matchup_period: int) -> list[int]:
    """Every scoring period in a matchup period, in order."""
    start = first_day(sched)
    if start is None:
        return []
    stretched = long_week(sched, start)
    return sorted({d for w in matchup_weeks(settings, matchup_period) for d in week_days(start, w, stretched)})


def current_matchup_days(
    settings: dict[str, Any], sched: ProSchedule, matchup_period: int, today: int,
) -> tuple[list[int], bool]:
    """Days of the matchup period ESPN says `today` is in, and whether they're exact.

    Usually that's `matchup_days`, which handles the All-Star week (see
    `long_week`). If ESPN ever stretches a week some other way, the calendar
    would run early from there on. When today falls outside the days we worked
    out, ESPN is telling us the matchup is still on: it runs at least through
    this Sunday. Then we return today through Sunday, and say they aren't exact
    (the matchup's first day is unknown, and it may not end this Sunday).
    """
    days = matchup_days(settings, sched, matchup_period)
    start = first_day(sched)
    if not days or start is None or today in days:
        return days, bool(days)
    sunday = today + 6 - day_date(start, today).weekday()
    return list(range(today, sunday + 1)), False


def remaining_days(settings: dict[str, Any], sched: ProSchedule, matchup_period: int, today: int) -> list[int]:
    """Scoring periods left in a matchup period, including today."""
    return [d for d in matchup_days(settings, sched, matchup_period) if d >= today]


def matchup_schedule(settings: dict[str, Any], sched: ProSchedule) -> list[dict[str, Any]]:
    """Each matchup period with its first and last day and their dates."""
    start = first_day(sched)
    periods = (settings.get("scheduleSettings") or {}).get("matchupPeriods") or {}
    out = []
    for mp in sorted(periods, key=int):
        days = matchup_days(settings, sched, int(mp))
        if start is None or not days:
            continue
        out.append({
            "week": int(mp), "first_day": days[0], "last_day": days[-1],
            "start": day_date(start, days[0]).isoformat(), "end": day_date(start, days[-1]).isoformat(),
        })
    return out
