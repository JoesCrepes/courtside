from datetime import date, datetime, timezone

from courtside.checkup import (
    best_starters, check_day, first_day, games_left, matchup_days, matchup_schedule, remaining_days,
)
from courtside.models import Player, ProGame, ProSchedule, Team

from conftest import BE, C, F, G, IR, PF, PG, SF, SG, UTIL

DAY = 10
PLAYS, RESTS = 1, 2  # NBA team ids: team 1 plays on DAY, team 2 doesn't
SCHED = ProSchedule(
    teams={1: "BOS", 2: "NYK", 3: "MIA"},
    games={DAY: {1: ProGame(1, DAY, 0, 1, 3), 3: ProGame(1, DAY, 0, 1, 3)},
           DAY + 1: {2: ProGame(2, DAY + 1, 0, 2, 3), 3: ProGame(2, DAY + 1, 0, 2, 3)}},
)


def player(pid, name, slot, eligible, *, avg=20.0, team=PLAYS, injury="ACTIVE", locked=False):
    return Player(id=pid, name=name, lineup_slot=slot, eligible_slots=eligible + [UTIL, BE, IR],
                  injury_status=injury, pro_team_id=team, lineup_locked=locked,
                  stats={"last15": {"avg": avg, "total": avg * 5, "gp": 5}})


def team(*players):
    return Team(id=3, name="Joe's Crepes", roster=list(players))


SMALL = {PG: 1, C: 1, UTIL: 1, BE: 3, IR: 1}


def kinds(findings):
    return [(f.severity, f.kind) for f in findings]


def test_best_starters_reroutes_to_fit_everyone():
    # Flex takes PG first (higher average); Pure must displace it to G.
    roster = [player(1, "Flex", BE, [PG, G], avg=30), player(2, "Pure", BE, [PG], avg=10)]
    best = best_starters(roster, {PG: 1, G: 1}, {1, 2})
    assert best == {1: G, 2: PG}


def test_best_starters_prefers_higher_average_and_skips_out_ir_and_no_game():
    roster = [
        player(1, "Low", BE, [C], avg=10), player(2, "High", BE, [C], avg=40),
        player(3, "Hurt", BE, [C], avg=50, injury="OUT"), player(4, "Idle", BE, [C], avg=60, team=RESTS),
        player(5, "Stashed", IR, [C], avg=70),
    ]
    assert best_starters(roster, {C: 1}, {1, 2, 3, 5}) == {2: C}


def test_locked_players_stay_put():
    roster = [player(1, "Started", C, [C], avg=5, locked=True), player(2, "Better", BE, [C], avg=50),
              player(3, "Too late", BE, [PG], avg=50, locked=True)]
    assert best_starters(roster, {C: 1, PG: 1}, {1, 2, 3}) == {1: C}
    assert best_starters(roster, {C: 1, PG: 1}, {1, 2, 3}, respect_locks=False) == {2: C, 3: PG}


def test_starter_without_game_should_sit_for_bench_player_with_one():
    t = team(player(1, "Point", PG, [PG]), player(2, "Idle Big", C, [C], team=RESTS),
             player(3, "Util", UTIL, [PF]), player(4, "Bench Big", BE, [C], avg=15))
    found = check_day(t, SCHED, DAY, SMALL)
    assert kinds(found) == [("action", "lineup"), ("warning", "no_game")]
    assert found[0].message.startswith("You can start 1 more player with games today. Start Bench Big (vs MIA)")
    assert found[0].message.endswith("sit Idle Big.")


def test_same_games_but_better_player_on_bench_is_info():
    t = team(player(1, "Point", PG, [PG]), player(2, "Weak Big", C, [C], avg=10),
             player(3, "Util", UTIL, [PF]), player(4, "Strong Big", BE, [C], avg=30))
    found = check_day(t, SCHED, DAY, SMALL)
    assert kinds(found) == [("info", "lineup")]
    assert "Strong Big (30.0)" in found[0].message and "Weak Big (10.0)" in found[0].message


def test_injuries_empty_slots_and_ir():
    t = team(
        player(1, "Out Starter", PG, [PG], injury="OUT"),
        player(2, "Iffy Big", C, [C], injury="DAY_TO_DAY"),
        player(3, "Healthy On IR", IR, [PF]),
        player(4, "Out On Bench", BE, [SF], injury="OUT"),
    )
    found = check_day(t, SCHED, DAY, {**SMALL, IR: 2})
    assert kinds(found) == [
        ("action", "injured_starter"), ("action", "empty_slot"), ("action", "ir_healthy"),
        ("warning", "uncertain_starter"), ("info", "ir_open"), ("info", "ir_open"),
    ]
    assert [f.players for f in found[-2:]] == [["Out Starter"], ["Out On Bench"]]


def test_clean_lineup_has_no_findings():
    t = team(player(1, "Point", PG, [PG]), player(2, "Big", C, [C]), player(3, "Util", UTIL, [PF]),
             player(4, "Spare", BE, [SG], team=RESTS))
    assert check_day(t, SCHED, DAY, SMALL) == []


def test_games_left_counts_best_lineup_each_day():
    t = team(player(1, "A", PG, [PG]), player(2, "B", C, [C], team=RESTS), player(3, "C", BE, [SF], team=RESTS))
    # DAY: only A plays. DAY+1: B and C play, and both fit (C and UTIL).
    assert games_left(t, SCHED, [DAY, DAY + 1], SMALL, DAY) == 3


# The 2026-27 season as ESPN lays it out for Joe's league: day 1 is Tue Oct 20,
# matchup 1 is Oct 20-25, matchup 5 is Nov 16-22, matchup 18 is Feb 15-28 (two
# ESPN weeks, over the All-Star break) and matchup 19 is Mar 1-7.
def ms(*args):
    return int(datetime(*args, tzinfo=timezone.utc).timestamp() * 1000)


SEASON = ProSchedule(teams={1: "BOS", 2: "NYK"}, games={
    # 10:30pm EDT on Oct 20 is already Oct 21 in UTC.
    1: {1: ProGame(1, 1, ms(2026, 10, 21, 2, 30), 1, 2), 2: ProGame(1, 1, ms(2026, 10, 21, 2, 30), 1, 2)},
    # 12pm EST on Thu Nov 19.
    31: {1: ProGame(2, 31, ms(2026, 11, 19, 17, 0), 2, 1), 2: ProGame(2, 31, ms(2026, 11, 19, 17, 0), 2, 1)},
})
WEEKS = {"scheduleSettings": {"matchupPeriods": {
    **{str(w): [w] for w in range(1, 18)}, "18": [18, 19], "19": [20]}}}


def test_first_day_comes_from_game_dates_in_eastern_time():
    assert first_day(SEASON) == date(2026, 10, 20)
    assert first_day(ProSchedule(teams={}, games={})) is None


def test_matchup_periods_are_espn_weeks_not_days():
    # ESPN's matchupPeriods says week 5 is [5]: ESPN week 5, which is days 28-34.
    assert matchup_days(WEEKS, SEASON, 5) == list(range(28, 35))
    # Week 1 starts on a Tuesday, so it's short.
    assert matchup_days(WEEKS, SEASON, 1) == list(range(1, 7))


def test_remaining_days_midweek():
    # Thursday Nov 19 is day 31; Sunday Nov 22 is the last day of matchup 5.
    assert remaining_days(WEEKS, SEASON, 5, 31) == [31, 32, 33, 34]
    assert remaining_days(WEEKS, SEASON, 5, 34) == [34]
    assert remaining_days(WEEKS, SEASON, 5, 35) == []


def test_remaining_days_without_settings_or_games():
    # No mapping: a matchup period is the ESPN week with the same number.
    assert remaining_days({}, SEASON, 5, 31) == [31, 32, 33, 34]
    assert remaining_days(WEEKS, ProSchedule(teams={}, games={}), 5, 31) == []


def test_matchup_schedule_dates():
    weeks = {w["week"]: w for w in matchup_schedule(WEEKS, SEASON)}
    assert weeks[1] == {"week": 1, "first_day": 1, "last_day": 6, "start": "2026-10-20", "end": "2026-10-25"}
    assert (weeks[5]["start"], weeks[5]["end"]) == ("2026-11-16", "2026-11-22")
    assert (weeks[18]["start"], weeks[18]["end"]) == ("2027-02-15", "2027-02-28")
    assert (weeks[19]["start"], weeks[19]["end"]) == ("2027-03-01", "2027-03-07")
