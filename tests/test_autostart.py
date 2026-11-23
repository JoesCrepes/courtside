import random

from courtside.autostart import can_play, start_active, start_active_for_day
from courtside.checkup import best_starters
from courtside.models import Player, ProGame, ProSchedule, Team

from conftest import BE, C, F, G, IR, PF, PG, SF, SG, UTIL

PLAYS, RESTS = 1, 2  # NBA team ids: team 1 plays on DAY, team 2 doesn't
DAY = 10
GAME = {1}


def player(pid, name, slot, eligible, *, avg=20.0, team=PLAYS, injury="ACTIVE", locked=False):
    return Player(id=pid, name=name, lineup_slot=slot, eligible_slots=eligible + [UTIL, BE, IR],
                  injury_status=injury, pro_team_id=team, lineup_locked=locked,
                  stats={"last15": {"avg": avg, "total": avg * 5, "gp": 5}})


def has_game(roster):
    return {p.id for p in roster if p.pro_team_id == PLAYS}


def run(roster, counts):
    return start_active(roster, counts, has_game(roster))


def moves(plan):
    return [(m.player_id, m.from_slot, m.to_slot) for m in plan.moves]


SMALL = {PG: 1, C: 1, UTIL: 1, BE: 3, IR: 1}


def test_no_game_starter_swaps_with_bench_player_who_plays():
    roster = [player(1, "Point", PG, [PG]), player(2, "Idle Big", C, [C], team=RESTS),
              player(3, "Util", UTIL, [PF]), player(4, "Bench Big", BE, [C])]
    plan = run(roster, SMALL)
    assert moves(plan) == [(4, BE, C), (2, C, BE)]
    assert [p.name for p in plan.started] == ["Bench Big"] and [p.name for p in plan.benched] == ["Idle Big"]


def test_out_starter_swaps_even_with_a_game():
    roster = [player(1, "Point", PG, [PG], injury="OUT"), player(2, "Big", C, [C]),
              player(3, "Util", UTIL, [PF]), player(4, "Bench Guard", BE, [PG])]
    assert moves(run(roster, SMALL)) == [(4, BE, PG), (1, PG, BE)]


def test_never_benches_a_healthy_starter_with_a_game():
    # Bench Star averages far more, but everyone starting can play: that's a judgment call, not ours.
    roster = [player(1, "Point", PG, [PG], avg=5), player(2, "Big", C, [C], avg=5),
              player(3, "Util", UTIL, [PF], avg=5), player(4, "Bench Star", BE, [PG, C], avg=60)]
    assert run(roster, SMALL).moves == []


def test_day_to_day_starter_stays_and_day_to_day_bench_player_can_start():
    roster = [player(1, "Iffy Point", PG, [PG], injury="DAY_TO_DAY"), player(2, "Idle Big", C, [C], team=RESTS),
              player(3, "Util", UTIL, [PF]), player(4, "Iffy Big", BE, [C], injury="QUESTIONABLE")]
    assert moves(run(roster, SMALL)) == [(4, BE, C), (2, C, BE)]


def test_shifts_a_starter_between_slots_to_make_room():
    # Only Bench Wing plays, and can't play C; Flex Big moves UTIL -> C so Wing can take UTIL.
    roster = [player(1, "Point", PG, [PG]), player(2, "Idle Big", C, [C], team=RESTS),
              player(3, "Flex Big", UTIL, [PF, C]), player(4, "Bench Wing", BE, [SF])]
    plan = run(roster, SMALL)
    assert sorted(moves(plan)) == sorted([(3, UTIL, C), (4, BE, UTIL), (2, C, BE)])
    assert [p.name for p in plan.shuffled] == ["Flex Big"]


def test_prefers_an_open_slot_to_shifting_anyone():
    roster = [player(1, "Point", PG, [PG, C]), player(3, "Util", UTIL, [PF]), player(4, "Bench Big", BE, [C])]
    assert moves(run(roster, SMALL)) == [(4, BE, C)]


def test_idle_starter_stays_when_nobody_can_replace_them():
    roster = [player(1, "Point", PG, [PG]), player(2, "Idle Big", C, [C], team=RESTS),
              player(3, "Util", UTIL, [PF]), player(4, "Bench Guard", BE, [PG], team=RESTS),
              player(5, "Hurt Big", BE, [C], injury="OUT")]
    plan = run(roster, SMALL)
    assert plan.moves == [] and [p.name for p in plan.idle] == ["Idle Big"]


def test_ir_is_never_touched():
    # A healthy player with a game stuck in IR is the owner's call; so is a bench player who could go to IR.
    roster = [player(1, "Point", PG, [PG]), player(2, "Idle Big", C, [C], team=RESTS),
              player(3, "Util", UTIL, [PF]), player(4, "Healthy On IR", IR, [C]),
              player(5, "Out On Bench", BE, [C], injury="OUT")]
    assert run(roster, SMALL).moves == []


def test_locked_players_stay_put():
    roster = [player(1, "Started", PG, [PG], injury="OUT", locked=True), player(2, "Idle Big", C, [C], team=RESTS),
              player(3, "Util", UTIL, [PF]), player(4, "Too Late Guard", BE, [PG], locked=True),
              player(5, "Bench Big", BE, [C])]
    assert moves(run(roster, SMALL)) == [(5, BE, C), (2, C, BE)]


def test_higher_average_starts_when_bench_has_more_than_open_slots():
    roster = [player(1, "Point", PG, [PG]), player(2, "Idle Big", C, [C], team=RESTS),
              player(3, "Util", UTIL, [PF]), player(4, "Low Big", BE, [C], avg=10),
              player(5, "High Big", BE, [C], avg=30)]
    assert moves(run(roster, SMALL)) == [(5, BE, C), (2, C, BE)]


def test_fills_empty_slots():
    roster = [player(1, "Bench Guard", BE, [PG]), player(2, "Bench Big", BE, [C])]
    assert sorted(moves(run(roster, SMALL))) == [(1, BE, PG), (2, BE, C)]


def test_for_day_uses_the_schedule():
    sched = ProSchedule(teams={1: "BOS", 2: "NYK", 3: "MIA"}, games={DAY: {1: ProGame(1, DAY, 0, 1, 3)}})
    t = Team(id=3, name="t", roster=[player(1, "Idle", C, [C], team=RESTS), player(2, "Bench", BE, [C])])
    assert moves(start_active_for_day(t, sched, DAY, {C: 1, BE: 1})) == [(2, BE, C), (1, C, BE)]


def apply(roster, plan):
    to = {m.player_id: m.to_slot for m in plan.moves}
    return [Player(**{**p.__dict__, "lineup_slot": to.get(p.id, p.lineup_slot)}) for p in roster]


FULL = {PG: 1, SG: 1, SF: 1, PF: 1, C: 1, G: 1, F: 1, UTIL: 3, BE: 3, IR: 1}
POSITIONS = [[PG], [PG, SG, G], [SG, SF, G, F], [SF, PF, F], [PF, C, F], [C]]


def random_roster(rng):
    slots = [s for s, n in FULL.items() if s not in (BE, IR) for _ in range(n)]
    rng.shuffle(slots)
    roster = []
    for pid in range(1, 15):
        elig = rng.choice(POSITIONS)
        open_fit = next((s for s in slots if s in elig + [UTIL]), None)
        slot = open_fit if open_fit is not None and rng.random() < 0.8 else (IR if rng.random() < 0.1 else BE)
        if slot not in (BE, IR):
            slots.remove(slot)
        roster.append(player(pid, f"P{pid}", slot, elig, avg=rng.uniform(5, 50),
                             team=rng.choice([PLAYS, PLAYS, RESTS]),
                             injury=rng.choice(["ACTIVE"] * 6 + ["OUT", "DAY_TO_DAY"])))
    return roster


def test_random_rosters_keep_the_promises():
    rng = random.Random(7)
    for _ in range(500):
        roster = random_roster(rng)
        games = has_game(roster)
        plan = start_active(roster, FULL, games)
        after = apply(roster, plan)
        by_id = {p.id: p for p in after}
        # Nobody who can play goes from starting to the bench; IR is untouched.
        for p in roster:
            q = by_id[p.id]
            if p.is_starting and can_play(p, games):
                assert q.is_starting
            assert (p.lineup_slot == IR) == (q.lineup_slot == IR)
            assert q.lineup_slot in (BE, IR) or q.lineup_slot in q.eligible_slots
        # Slots aren't overfilled.
        for sid, n in FULL.items():
            if sid not in (BE, IR):
                assert sum(q.lineup_slot == sid for q in after) <= n
        # As many players who can play start as any lineup allows.
        active = sum(q.is_starting and can_play(q, games) for q in after)
        assert active == len(best_starters(roster, FULL, games, respect_locks=False))
        # Running it again changes nothing.
        assert start_active(after, FULL, games).moves == []


def test_benches_the_out_player_and_keeps_the_star_who_only_has_an_off_day():
    # ESPN carries the lineup into tomorrow, so Star (no game today) keeps PF; Hurt (OUT) and the
    # weaker idle wing go to the bench. Swing moves to UTIL to free PF rather than benching Star.
    counts = {SF: 1, PF: 1, UTIL: 2, BE: 3, IR: 1}
    roster = [player(1, "Star", PF, [PF], avg=60, team=RESTS), player(2, "Idle Wing", SF, [SF], avg=24, team=RESTS),
              player(3, "Hurt", UTIL, [PF], avg=41, injury="OUT"), player(4, "Util", UTIL, [SF]),
              player(5, "Wing", BE, [SF], avg=38), player(6, "Swing", BE, [SF, PF], avg=19)]
    plan = run(roster, counts)
    assert sorted(moves(plan)) == sorted([(5, BE, SF), (6, BE, UTIL), (2, SF, BE), (3, UTIL, BE)])
    assert [p.name for p in plan.idle] == ["Star"]
