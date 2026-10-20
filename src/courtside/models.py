"""Thin typed views over ESPN's league JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .slots import NON_STARTING, slot_name


@dataclass
class Player:
    id: int
    name: str
    lineup_slot: int
    eligible_slots: list[int]
    injury_status: str = "ACTIVE"
    pro_team_id: int | None = None
    percent_owned: float | None = None

    @property
    def is_starting(self) -> bool:
        return self.lineup_slot not in NON_STARTING

    @property
    def slot(self) -> str:
        return slot_name(self.lineup_slot)

    @classmethod
    def from_roster_entry(cls, entry: dict[str, Any]) -> "Player":
        p = entry["playerPoolEntry"]["player"]
        return cls(
            id=entry["playerId"],
            name=p.get("fullName", str(entry["playerId"])),
            lineup_slot=entry["lineupSlotId"],
            eligible_slots=list(p.get("eligibleSlots", [])),
            injury_status=p.get("injuryStatus") or "ACTIVE",
            pro_team_id=p.get("proTeamId"),
            percent_owned=(p.get("ownership") or {}).get("percentOwned"),
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
        )


@dataclass
class Team:
    id: int
    name: str
    abbrev: str = ""
    roster: list[Player] = field(default_factory=list)

    @classmethod
    def from_json(cls, t: dict[str, Any]) -> "Team":
        # ESPN has used both "name" and "location"+"nickname" over the years.
        name = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
        entries = (t.get("roster") or {}).get("entries", [])
        return cls(
            id=t["id"],
            name=name or f"Team {t['id']}",
            abbrev=t.get("abbrev", ""),
            roster=[Player.from_roster_entry(e) for e in entries],
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
