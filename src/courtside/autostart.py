"""Start active players: the lineup moves that need no judgment.

ESPN's web app has a "Start Active Players" button. It has no endpoint of its
own that we know of; the page works out lineup moves and posts them as an
ordinary ROSTER transaction, the same kind `lineup_payload` builds. This is
our version, kept deliberately narrower than "best lineup" so it is safe to
run without anyone looking at it first:

- A starter who can play today (has a game and isn't OUT, IR or suspended)
  always stays in the starting lineup. They may move to another starting
  slot to make room, but never to the bench. So a healthy player with a
  game is never benched, whatever their average.
- A starter who can't play (no game, or OUT/IR/suspended) gives up their
  slot to a bench player who can play. If nobody on the bench can take it,
  they stay where they are. When several could give up a slot, the one who
  goes to the bench is OUT before merely idle, then the lower average, since
  ESPN carries today's lineup into later days.
- Only bench players move up. IR is never touched, nobody is added,
  dropped, claimed or traded, and locked players (game started) stay put.

When more bench players can play than there are open slots, the higher
fantasy average starts first, as in `best_starters`. That is the only
ordering choice, and it only ever picks between players who would otherwise
score nothing from the bench.

Everything here is pure; the caller fetches the team and schedule.
"""

from __future__ import annotations

from dataclasses import dataclass

from .checkup import CANT_PLAY, games_on, starting_slots, value
from .models import Player, ProSchedule, Team
from .slots import BENCH, IR, slot_name
from .transactions import LineupMove


@dataclass
class AutoStart:
    """What start-active-players would do for one day."""

    moves: list[LineupMove]
    started: list[Player]  # bench players moved into the lineup
    benched: list[Player]  # starters who can't play, moved to the bench
    shuffled: list[Player]  # starters moved between starting slots to make room
    idle: list[Player]  # starters who can't play and stay, because nobody on the bench can replace them


def can_play(p: Player, has_game: set[int]) -> bool:
    return p.id in has_game and p.injury_status not in CANT_PLAY


def start_active(roster: list[Player], slot_counts: dict[int, int], has_game: set[int]) -> AutoStart:
    slots = starting_slots(slot_counts)
    owner: list[int | None] = [None] * len(slots)  # slot index -> player id
    by_id = {p.id: p for p in roster}

    def seat(p: Player) -> bool:
        i = next((i for i, s in enumerate(slots) if s == p.lineup_slot and owner[i] is None), None)
        if i is not None:
            owner[i] = p.id
        return i is not None

    # Everyone starting who can play, and everyone locked, keeps a seat. The
    # rest of the starters (can't play, not locked) leave their seats open.
    out: list[Player] = []
    for p in roster:
        if not p.is_starting or p.lineup_slot < 0:
            continue
        if can_play(p, has_game) or p.lineup_locked:
            seat(p)
        else:
            out.append(p)

    # A starter who can't play may keep their own slot, but never moves to another.
    stay_put = {p.id for p in out}

    def allowed(pid: int) -> set[int]:
        return {by_id[pid].lineup_slot} if pid in stay_put else set(by_id[pid].eligible_slots)

    def fits(pid: int, seen: set[int]) -> bool:
        """Seat pid, moving seated players between starting slots if needed (never off them)."""
        open_first = sorted(
            (i for i, s in enumerate(slots) if s in allowed(pid) and i not in seen),
            key=lambda i: owner[i] is not None,  # an empty slot needs no one else to move
        )
        for i in open_first:
            seen.add(i)
            cur = owner[i]
            if cur is None or (not by_id[cur].lineup_locked and fits(cur, seen)):
                owner[i] = pid
                return True
        return False

    bench = [p for p in roster if p.lineup_slot == BENCH and can_play(p, has_game) and not p.lineup_locked]
    for p in sorted(bench, key=value, reverse=True):
        fits(p.id, set())

    # Starters who can't play keep their slot whenever there's still room, shifting others
    # to make it. ESPN carries a lineup forward to later days, so a star benched today on an
    # off day would still be on the bench tomorrow, where this tool won't start them over a
    # healthy starter. So the seats that go are those of whoever matters least: OUT before
    # no game, then the lower average.
    for p in sorted(out, key=lambda p: (p.injury_status not in CANT_PLAY, value(p)), reverse=True):
        fits(p.id, set())
    idle = [p for p in out if p.id in set(owner)]

    final = {pid: slots[i] for i, pid in enumerate(owner) if pid is not None}
    ins = [LineupMove(pid, by_id[pid].lineup_slot, sid) for pid, sid in final.items() if by_id[pid].lineup_slot != sid]
    outs = [LineupMove(p.id, p.lineup_slot, BENCH) for p in out if p.id not in final]

    # The guarantees, checked rather than assumed.
    for m in ins + outs:
        p = by_id[m.player_id]
        broken = (
            "would touch IR" if IR in (m.from_slot, m.to_slot)
            else "is locked" if p.lineup_locked
            else "can play and would be benched" if m.to_slot == BENCH and can_play(p, has_game)
            else f"isn't eligible for {slot_name(m.to_slot)}" if m.to_slot != BENCH and m.to_slot not in p.eligible_slots
            else None
        )
        if broken:
            raise RuntimeError(f"start_active bug: {p.name} {broken}; nothing was submitted")

    return AutoStart(
        # Moves into starting slots first, then to the bench, as ESPN's own swaps are ordered.
        moves=ins + outs,
        started=[by_id[m.player_id] for m in ins if m.from_slot == BENCH],
        benched=[by_id[m.player_id] for m in outs],
        shuffled=[by_id[m.player_id] for m in ins if m.from_slot != BENCH],
        idle=idle,
    )


def start_active_for_day(team: Team, sched: ProSchedule, day: int, slot_counts: dict[int, int]) -> AutoStart:
    return start_active(team.roster, slot_counts, games_on(day, team.roster, sched))
