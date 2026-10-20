"""Command-line interface. Every write is a dry run unless --execute is passed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import EspnClient, EspnError
from .config import Config
from .slots import slot_id, slot_name
from .transactions import LineupError, compare_payloads, rebuild_from_capture


def _print_json(obj: object) -> None:
    print(json.dumps(obj, indent=2))


def cmd_roster(client: EspnClient, args: argparse.Namespace) -> None:
    team = client.team(args.team, scoring_period=args.day)
    print(f"{team.name} ({team.abbrev})")
    for p in sorted(team.roster, key=lambda p: (not p.is_starting, p.lineup_slot)):
        inj = "" if p.injury_status == "ACTIVE" else f"  [{p.injury_status}]"
        elig = "/".join(slot_name(s) for s in p.eligible_slots if s < 12)
        print(f"  {p.slot:>5}  {p.name:<26} {p.id:>8}  {elig}{inj}")


def cmd_fa(client: EspnClient, args: argparse.Namespace) -> None:
    for p in client.free_agents(limit=args.limit, position=args.pos):
        own = f"{p.percent_owned:5.1f}%" if p.percent_owned is not None else "     -"
        inj = "" if p.injury_status == "ACTIVE" else f"  [{p.injury_status}]"
        print(f"  {own}  {p.name:<26} {p.id:>8}{inj}")


def cmd_move(client: EspnClient, args: argparse.Namespace) -> None:
    _print_json(client.move(args.player, slot_id(args.slot), scoring_period=args.day, execute=args.execute))


def cmd_add(client: EspnClient, args: argparse.Namespace) -> None:
    drop_id = None
    if args.drop:
        drop_id = client.team().find(args.drop).id
    _print_json(
        client.add_drop(args.player_id, drop_id, waiver=args.waiver, bid=args.bid, execute=args.execute)
    )


def cmd_drop(client: EspnClient, args: argparse.Namespace) -> None:
    drop_id = client.team().find(args.player).id
    _print_json(client.add_drop(None, drop_id, execute=args.execute))


def cmd_compare(args: argparse.Namespace) -> int:
    captured = json.loads(Path(args.captured).read_text())
    diffs = compare_payloads(captured, rebuild_from_capture(captured))
    if not diffs:
        print(f"OK: our {captured.get('type')} builder matches the capture exactly")
        return 0
    print(f"MISMATCH ({len(diffs)}):")
    for d in diffs:
        print(f"  - {d}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="courtside", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("roster", help="show a roster")
    p.add_argument("--team", type=int, help="team id (default: ESPN_TEAM_ID)")
    p.add_argument("--day", type=int, help="scoring period id (default: today)")

    p = sub.add_parser("fa", help="list top free agents")
    p.add_argument("--pos", help="PG, SG, SF, PF, C, G, F, UTIL")
    p.add_argument("--limit", type=int, default=25)

    p = sub.add_parser("move", help="move a player to a lineup slot")
    p.add_argument("player", help="player id or name fragment")
    p.add_argument("slot", help="PG, SG, SF, PF, C, G, F, UTIL, BE, IR or numeric id")
    p.add_argument("--day", type=int, help="scoring period id (default: today)")
    p.add_argument("--execute", action="store_true")

    p = sub.add_parser("add", help="add a free agent (optionally dropping someone)")
    p.add_argument("player_id", type=int)
    p.add_argument("--drop", help="rostered player id or name fragment")
    p.add_argument("--waiver", action="store_true", help="submit as a waiver claim")
    p.add_argument("--bid", type=int, help="FAAB bid for waiver claims")
    p.add_argument("--execute", action="store_true")

    p = sub.add_parser("drop", help="drop a rostered player")
    p.add_argument("player", help="player id or name fragment")
    p.add_argument("--execute", action="store_true")

    p = sub.add_parser("compare", help="check our payload builder against a captured request body")
    p.add_argument("captured", help="JSON file copied from DevTools (Request Payload)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "compare":
        return cmd_compare(args)
    client = EspnClient(Config.from_env())
    handler = {
        "roster": cmd_roster, "fa": cmd_fa, "move": cmd_move, "add": cmd_add, "drop": cmd_drop,
    }[args.cmd]
    try:
        handler(client, args)
    except (EspnError, LineupError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
