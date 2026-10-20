"""A small fake of ESPN's read/write endpoints, built on `responses`."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from courtside import Config, EspnClient
from courtside.client import READS, WRITES

LEAGUE_ID = 123456
SEASON = 2027
TEAM_ID = 3
SWID = "{AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE}"
TODAY = 4  # scoring period (day) id

PG, SG, SF, PF, C, G, F, UTIL, BE, IR = 0, 1, 2, 3, 4, 5, 6, 11, 12, 13


def entry(pid: int, name: str, slot: int, eligible: list[int], injury: str = "ACTIVE") -> dict:
    return {
        "playerId": pid,
        "lineupSlotId": slot,
        "playerPoolEntry": {
            "player": {
                "fullName": name,
                "eligibleSlots": eligible + [UTIL, BE, IR],
                "injuryStatus": injury,
                "proTeamId": 1,
                "ownership": {"percentOwned": 99.0},
            }
        },
    }


def my_roster() -> list[dict]:
    return [
        entry(101, "Point Guard Paul", PG, [PG, G]),
        entry(102, "Shooting Sam", SG, [PG, SG, G]),
        entry(103, "Wing Wally", SF, [SG, SF, G]),  # NOT F-eligible
        entry(104, "Power Pete", PF, [PF, F]),
        entry(105, "Center Cal", C, [C]),
        entry(106, "Guard Gus", G, [PG, SG, G]),
        entry(107, "Forward Fran", F, [SF, PF, F]),
        entry(108, "Utility Ursula", UTIL, [PF, C, F]),
        entry(109, "Bench Ben", BE, [PG, SG, SF, G, F]),
        entry(110, "Bench Bigs", BE, [C]),
        entry(111, "Injured Ivan", IR, [SF, PF, F], injury="OUT"),
    ]


LEAGUE_VIEWS = {
    "mStatus": {"scoringPeriodId": TODAY, "status": {"latestScoringPeriod": TODAY}},
    "mSettings": {
        "settings": {
            "name": "Test League",
            "rosterSettings": {
                "lineupSlotCounts": {
                    str(PG): 1, str(SG): 1, str(SF): 1, str(PF): 1, str(C): 1,
                    str(G): 1, str(F): 1, "7": 0, "8": 0, "9": 0, "10": 0,
                    str(UTIL): 3, str(BE): 3, str(IR): 1,
                }
            },
        }
    },
}


def teams_view() -> dict:
    return {
        "teams": [
            {"id": 1, "location": "Other", "nickname": "Team", "abbrev": "OTH", "roster": {"entries": []}},
            {"id": TEAM_ID, "name": "Joe's Crepes", "abbrev": "JOE", "roster": {"entries": my_roster()}},
        ]
    }


FREE_AGENTS = {
    "players": [
        {"id": 201, "player": {"fullName": "Free Fred", "eligibleSlots": [PG, G, UTIL, BE],
                               "ownership": {"percentOwned": 42.5}}},
        {"id": 202, "status": "WAIVERS", "player": {"fullName": "Waiver Will", "eligibleSlots": [C, UTIL, BE],
                               "injuryStatus": "DAY_TO_DAY", "ownership": {"percentOwned": 12.0}}},
    ]
}


class FakeEspn:
    def __init__(self, rsps: responses.RequestsMock):
        self.rsps = rsps
        self.posts: list[dict] = []
        self.write_status = 200
        self.write_body: dict = {"id": "txn-1", "status": "EXECUTED"}
        self.read_status = 200
        base = f"/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"
        self.reads_url = READS + base
        self.writes_url = WRITES + base + "/transactions/"
        rsps.add_callback(responses.GET, self.reads_url, callback=self._read)
        rsps.add_callback(responses.POST, self.writes_url, callback=self._write)

    def _read(self, request):
        if self.read_status != 200:
            return (self.read_status, {}, json.dumps({"messages": ["nope"]}))
        views = parse_qs(urlparse(request.url).query).get("view", [])
        body: dict = {"id": LEAGUE_ID, "seasonId": SEASON}
        for v in views:
            if v in ("mTeam", "mRoster"):
                body.update(teams_view())
            elif v == "kona_player_info":
                body.update(FREE_AGENTS)
            else:
                body.update(LEAGUE_VIEWS.get(v, {}))
        return (200, {"Content-Type": "application/json"}, json.dumps(body))

    def _write(self, request):
        self.posts.append(json.loads(request.body))
        return (self.write_status, {"Content-Type": "application/json"}, json.dumps(self.write_body))


@pytest.fixture
def config() -> Config:
    return Config(
        league_id=LEAGUE_ID, season=SEASON, team_id=TEAM_ID,
        espn_s2="AEfakeS2cookie", swid=SWID, write_enabled=True,
    )


@pytest.fixture
def fake():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield FakeEspn(rsps)


@pytest.fixture
def client(config, fake) -> EspnClient:
    return EspnClient(config)
