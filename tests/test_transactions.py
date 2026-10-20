import json
from pathlib import Path

import pytest

from courtside.models import Team
from courtside.transactions import (
    LineupError,
    LineupMove,
    compare_payloads,
    free_agent_payload,
    lineup_payload,
    plan_move,
    rebuild_from_capture,
    slot_counts_from_settings,
    waiver_payload,
)

from conftest import BE, C, F, G, IR, LEAGUE_VIEWS, PG, SF, SWID, TEAM_ID, UTIL, my_roster

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def team() -> Team:
    return Team.from_json({"id": TEAM_ID, "name": "Joe's Crepes", "roster": {"entries": my_roster()}})


@pytest.fixture
def counts() -> dict[int, int]:
    return slot_counts_from_settings(LEAGUE_VIEWS["mSettings"]["settings"])


# ---- payload shapes --------------------------------------------------------

def test_lineup_payload_shape():
    body = lineup_payload(TEAM_ID, SWID, 4, [LineupMove(109, BE, PG), LineupMove(101, PG, BE)])
    assert body == {
        "isLeagueManager": False,
        "teamId": TEAM_ID,
        "type": "ROSTER",
        "memberId": SWID,
        "scoringPeriodId": 4,
        "executionType": "EXECUTE",
        "items": [
            {"playerId": 109, "type": "LINEUP", "fromLineupSlotId": BE, "toLineupSlotId": PG},
            {"playerId": 101, "type": "LINEUP", "fromLineupSlotId": PG, "toLineupSlotId": BE},
        ],
    }


def test_lineup_payload_rejects_empty():
    with pytest.raises(LineupError):
        lineup_payload(TEAM_ID, SWID, 4, [])


def test_free_agent_add_and_drop():
    body = free_agent_payload(TEAM_ID, SWID, 4, add_id=201, drop_id=110)
    assert body["type"] == "FREEAGENT"
    assert body["items"] == [
        {"playerId": 201, "type": "ADD", "toTeamId": TEAM_ID},
        {"playerId": 110, "type": "DROP", "fromTeamId": TEAM_ID},
    ]
    assert "bidAmount" not in body


def test_free_agent_add_only_and_drop_only():
    assert [i["type"] for i in free_agent_payload(TEAM_ID, SWID, 4, 201, None)["items"]] == ["ADD"]
    assert [i["type"] for i in free_agent_payload(TEAM_ID, SWID, 4, None, 110)["items"]] == ["DROP"]


def test_free_agent_needs_someone():
    with pytest.raises(ValueError):
        free_agent_payload(TEAM_ID, SWID, 4, None, None)


@pytest.mark.parametrize("bid", [None, 0, 17])
def test_waiver_bid(bid):
    body = waiver_payload(TEAM_ID, SWID, 4, add_id=202, drop_id=110, bid_amount=bid)
    assert body["type"] == "WAIVER"
    assert body["bidAmount"] == bid
    assert len(body["items"]) == 2


# ---- lineup planning -------------------------------------------------------

def test_move_into_slot_with_room(team, counts):
    # UTIL holds 3 and only Ursula is there.
    assert plan_move(team, 110, UTIL, counts) == [LineupMove(110, BE, UTIL)]


def test_bench_to_full_slot_benches_occupant(team, counts):
    assert plan_move(team, 109, PG, counts) == [
        LineupMove(109, BE, PG),
        LineupMove(101, PG, BE),
    ]


def test_starter_swap_when_occupant_eligible(team, counts):
    # Gus (G) -> PG; Paul is G-eligible so they trade places.
    assert plan_move(team, 106, PG, counts) == [
        LineupMove(106, G, PG),
        LineupMove(101, PG, G),
    ]


def test_starter_swap_when_occupant_ineligible_benches_them(team, counts):
    # Fran (F) -> SF; Wally isn't F-eligible, so Wally goes to the bench.
    assert plan_move(team, 107, SF, counts) == [
        LineupMove(107, F, SF),
        LineupMove(103, SF, BE),
    ]


def test_activate_from_ir_never_puts_healthy_player_on_ir(team, counts):
    assert plan_move(team, 111, SF, counts) == [
        LineupMove(111, IR, SF),
        LineupMove(103, SF, BE),
    ]


def test_move_to_bench_is_single_move(team, counts):
    assert plan_move(team, 105, BE, counts) == [LineupMove(105, C, BE)]


def test_ineligible_slot(team, counts):
    with pytest.raises(LineupError, match="not eligible"):
        plan_move(team, 105, PG, counts)


def test_already_in_slot(team, counts):
    with pytest.raises(LineupError, match="already"):
        plan_move(team, 101, PG, counts)


def test_slot_league_does_not_use(team, counts):
    t = Team.from_json({"id": TEAM_ID, "name": "x", "roster": {"entries": my_roster()}})
    t.player(103).eligible_slots.append(7)  # SG/SF, count 0 in this league
    with pytest.raises(LineupError, match="no SG/SF slot"):
        plan_move(t, 103, 7, counts)


def test_unknown_player(team, counts):
    with pytest.raises(KeyError):
        plan_move(team, 999, PG, counts)


# ---- capture comparison ----------------------------------------------------

def test_compare_identical_is_clean():
    body = free_agent_payload(TEAM_ID, SWID, 4, 201, 110)
    assert compare_payloads(body, json.loads(json.dumps(body))) == []


def test_compare_ignores_volatile_values_but_not_keys():
    a = free_agent_payload(TEAM_ID, SWID, 4, 201, 110)
    b = free_agent_payload(TEAM_ID, "{OTHER}", 99, 201, 110)
    assert compare_payloads(a, b) == []
    del b["scoringPeriodId"]
    assert compare_payloads(a, b) == ["missing in ours: scoringPeriodId (captured: 4)"]


def test_compare_reports_value_and_length_diffs():
    a = free_agent_payload(TEAM_ID, SWID, 4, 201, 110)
    b = free_agent_payload(TEAM_ID, SWID, 4, 201, None)
    b["extra"] = True
    diffs = compare_payloads(a, b)
    assert "items: captured has 2 items, ours has 1" in diffs
    assert "extra in ours: extra = True" in diffs


@pytest.mark.parametrize("name", ["captured_lineup.json", "captured_freeagent.json", "captured_waiver.json"])
def test_rebuild_matches_reference_captures(name):
    captured = json.loads((FIXTURES / name).read_text())
    assert compare_payloads(captured, rebuild_from_capture(captured)) == []


def test_rebuild_unknown_type():
    with pytest.raises(ValueError):
        rebuild_from_capture({"teamId": 1, "type": "TRADE_PROPOSAL", "items": []})


def test_healthy_player_cannot_go_on_ir(team, counts):
    with pytest.raises(LineupError, match="only OUT players"):
        plan_move(team, 105, IR, counts)


def test_swap_with_picks_the_occupant(team, counts):
    team.player(110).lineup_slot = UTIL
    team.player(104).lineup_slot = UTIL  # UTIL now full: Ursula, Bigs, Pete
    assert plan_move(team, 109, UTIL, counts, swap_with=104) == [
        LineupMove(109, BE, UTIL),
        LineupMove(104, UTIL, BE),
    ]


def test_swap_with_rejects_non_occupant_or_open_slot(team, counts):
    with pytest.raises(LineupError, match="is not in PG"):
        plan_move(team, 109, PG, counts, swap_with=105)
    with pytest.raises(LineupError, match="has room"):
        plan_move(team, 110, UTIL, counts, swap_with=108)
