"""Configuration loaded from environment variables (or a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we don't need python-dotenv. Existing env wins."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    league_id: int
    season: int
    team_id: int | None = None
    espn_s2: str | None = None
    swid: str | None = None
    # Writes stay off unless explicitly enabled, even when --execute is passed.
    write_enabled: bool = False

    @classmethod
    def from_env(cls, dotenv: Path | None = Path(".env")) -> "Config":
        if dotenv is not None:
            _load_dotenv(dotenv)
        try:
            league_id = int(os.environ["ESPN_LEAGUE_ID"])
        except KeyError as e:
            raise SystemExit("ESPN_LEAGUE_ID is not set (see .env.example)") from e
        team = os.environ.get("ESPN_TEAM_ID")
        swid = os.environ.get("ESPN_SWID")
        if swid and not swid.startswith("{"):
            swid = "{" + swid.strip("{}") + "}"
        return cls(
            league_id=league_id,
            # ESPN names a season by the year it ends: 2026-27 is 2027.
            season=int(os.environ.get("ESPN_SEASON", "2027")),
            team_id=int(team) if team else None,
            espn_s2=os.environ.get("ESPN_S2"),
            swid=swid,
            write_enabled=os.environ.get("ESPN_WRITE_ENABLED", "").lower() in ("1", "true", "yes"),
        )
