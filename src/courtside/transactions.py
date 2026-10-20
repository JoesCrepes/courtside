"""Payload builders for ESPN's write endpoint.

Everything here is pure: it turns intent ("start Player X at PG") into the
JSON body ESPN's web app POSTs to lm-api-writes.../transactions/. Nothing in
this module touches the network, so it can be tested exhaustively.

Payload shapes come from public projects that captured them from the browser.
They are NOT officially documented; verify each against a capture from your
own league with `courtside compare` before trusting it (see docs/CAPTURE.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .models import Team
from .slots import BENCH, IR, IR_ELIGIBLE, slot_name


class LineupError(ValueError):
    pass


@dataclass(frozen=True)
class LineupMove:
    player_id: int
    from_slot: int
    to_slot: int


def _envelope(
    *, team_id: int, member_id: str, scoring_period: int, type_: str, items: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "isLeagueManager": False,
        "teamId": team_id,
        "type": type_,
        "memberId": member_id,
        "scoringPeriodId": scoring_period,
        "executionType": "EXECUTE",
        "items": items,
    }


def lineup_payload(
    team_id: int, member_id: str, scoring_period: int, moves: list[LineupMove]
) -> dict[str, Any]:
    if not moves:
        raise LineupError("no lineup moves to submit")
    # Verified against a live capture (Oct 2026): unlike add/drop items,
    # lineup items carry no fromTeamId/toTeamId.
    items = [
        {
            "playerId": m.player_id,
            "type": "LINEUP",
            "fromLineupSlotId": m.from_slot,
            "toLineupSlotId": m.to_slot,
        }
        for m in moves
    ]
    return _envelope(
        team_id=team_id, member_id=member_id, scoring_period=scoring_period, type_="ROSTER", items=items
    )


def _add_drop_items(team_id: int, add_id: int | None, drop_id: int | None) -> list[dict[str, Any]]:
    if add_id is None and drop_id is None:
        raise ValueError("need a player to add, drop, or both")
    items: list[dict[str, Any]] = []
    if add_id is not None:
        items.append({"playerId": add_id, "type": "ADD", "toTeamId": team_id})
    if drop_id is not None:
        items.append({"playerId": drop_id, "type": "DROP", "fromTeamId": team_id})
    return items


def free_agent_payload(
    team_id: int, member_id: str, scoring_period: int, add_id: int | None, drop_id: int | None
) -> dict[str, Any]:
    return _envelope(
        team_id=team_id,
        member_id=member_id,
        scoring_period=scoring_period,
        type_="FREEAGENT",
        items=_add_drop_items(team_id, add_id, drop_id),
    )


def waiver_payload(
    team_id: int,
    member_id: str,
    scoring_period: int,
    add_id: int,
    drop_id: int | None,
    bid_amount: int | None = None,
) -> dict[str, Any]:
    body = _envelope(
        team_id=team_id,
        member_id=member_id,
        scoring_period=scoring_period,
        type_="WAIVER",
        items=_add_drop_items(team_id, add_id, drop_id),
    )
    body["bidAmount"] = bid_amount
    return body


def plan_move(
    team: Team, player_id: int, to_slot: int, slot_counts: dict[int, int], swap_with: int | None = None
) -> list[LineupMove]:
    """Work out the moves needed to put a player in a slot.

    If the slot has room, it's a single move. If it's full, swap with an
    occupant who can fill the player's old slot, or else bench the occupant.
    Mirrors what ESPN's own UI does when you tap "MOVE" then a filled slot.
    `swap_with` picks which occupant gives up the slot.
    """
    player = team.player(player_id)
    if player.lineup_slot == to_slot:
        raise LineupError(f"{player.name} is already in {slot_name(to_slot)}")
    if to_slot not in (BENCH, IR) and to_slot not in player.eligible_slots:
        raise LineupError(f"{player.name} is not eligible for {slot_name(to_slot)}")
    if to_slot == IR and player.injury_status not in IR_ELIGIBLE:
        raise LineupError(f"{player.name} is {player.injury_status}; only OUT players can go on IR")

    capacity = slot_counts.get(to_slot, 0)
    if to_slot != BENCH and capacity == 0:
        raise LineupError(f"this league has no {slot_name(to_slot)} slot")

    occupants = [p for p in team.roster if p.lineup_slot == to_slot and p.id != player_id]
    move = LineupMove(player_id, player.lineup_slot, to_slot)
    if to_slot == BENCH or len(occupants) < capacity:
        if swap_with is not None:
            raise LineupError(f"{slot_name(to_slot)} has room; no swap needed")
        return [move]
    if swap_with is not None:
        occupants = [p for p in occupants if p.id == swap_with]
        if not occupants:
            other = team.player(swap_with)
            raise LineupError(f"{other.name} is not in {slot_name(to_slot)}")

    from_slot = player.lineup_slot
    if from_slot != IR:
        for occ in occupants:
            if from_slot == BENCH or from_slot in occ.eligible_slots:
                return [move, LineupMove(occ.id, to_slot, from_slot)]
    # Nobody can take the vacated slot (or it was IR, which a healthy
    # starter can't fill); send the first occupant to the bench.
    occ = occupants[0]
    return [move, LineupMove(occ.id, to_slot, BENCH)]


def slot_counts_from_settings(settings: dict[str, Any]) -> dict[int, int]:
    raw = settings["rosterSettings"]["lineupSlotCounts"]
    return {int(k): int(v) for k, v in raw.items()}


def captures_from_har(har: dict[str, Any]) -> list[dict[str, Any]]:
    """Request bodies of every transaction POST in a DevTools HAR export."""
    return [
        json.loads(e["request"]["postData"]["text"])
        for e in har["log"]["entries"]
        if e["request"]["method"] == "POST"
        and "/transactions/" in e["request"]["url"]
        and e["request"].get("postData", {}).get("text")
    ]


def rebuild_from_capture(captured: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a captured body from its intent using our builders.

    If compare_payloads(captured, rebuild_from_capture(captured)) is empty,
    our builder produces exactly what ESPN's web app sends for that action.
    """
    team_id = captured["teamId"]
    member = captured.get("memberId", "")
    period = captured.get("scoringPeriodId", 0)
    items = captured.get("items", [])
    kind = captured.get("type")
    if kind == "ROSTER":
        moves = [
            LineupMove(i["playerId"], i.get("fromLineupSlotId", -1), i.get("toLineupSlotId", -1))
            for i in items
        ]
        return lineup_payload(team_id, member, period, moves)
    add = next((i["playerId"] for i in items if i.get("type") == "ADD"), None)
    drop = next((i["playerId"] for i in items if i.get("type") == "DROP"), None)
    if kind == "FREEAGENT":
        return free_agent_payload(team_id, member, period, add, drop)
    if kind == "WAIVER":
        return waiver_payload(team_id, member, period, add, drop, captured.get("bidAmount"))
    raise ValueError(f"no builder for transaction type {kind!r}")


# Keys whose values legitimately differ between a capture and a fresh build.
VOLATILE_KEYS = {"scoringPeriodId", "memberId"}


def compare_payloads(captured: Any, built: Any, path: str = "") -> list[str]:
    """Structural diff between a browser-captured body and one we built.

    Returns human-readable differences. Ignores values of VOLATILE_KEYS but
    still requires the keys themselves to exist.
    """
    diffs: list[str] = []
    if isinstance(captured, dict) and isinstance(built, dict):
        for k in sorted(set(captured) | set(built)):
            p = f"{path}.{k}" if path else k
            if k not in built:
                diffs.append(f"missing in ours: {p} (captured: {captured[k]!r})")
            elif k not in captured:
                diffs.append(f"extra in ours: {p} = {built[k]!r}")
            elif k not in VOLATILE_KEYS:
                diffs.extend(compare_payloads(captured[k], built[k], p))
    elif isinstance(captured, list) and isinstance(built, list):
        if len(captured) != len(built):
            diffs.append(f"{path}: captured has {len(captured)} items, ours has {len(built)}")
        for i, (c, b) in enumerate(zip(captured, built)):
            diffs.extend(compare_payloads(c, b, f"{path}[{i}]"))
    elif captured != built:
        diffs.append(f"{path}: captured {captured!r}, ours {built!r}")
    return diffs
