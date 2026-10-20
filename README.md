# courtside

An alternative client for ESPN Fantasy Basketball. It reads your league and can
**set lineups, add/drop free agents, and submit waiver claims** through ESPN's
undocumented write API (`lm-api-writes.fantasy.espn.com`), the same one ESPN's
own web app uses.

> Unofficial. Not affiliated with ESPN. ESPN can change these endpoints at any
> time, and automating moves at scale may violate their terms. Use it for your
> own team, at human speed.

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env   # then fill it in
```

To get `ESPN_S2` and `ESPN_SWID`: log into fantasy.espn.com, open DevTools →
Application → Cookies → `https://fantasy.espn.com`, and copy `espn_s2` and
`SWID`. Your league id is in the league URL (`leagueId=...`), and your team id
is in your team page URL (`teamId=...`).

## Usage

```bash
courtside roster                 # today's lineup
courtside roster --day 10        # lineup for scoring period (day) 10
courtside fa --pos C             # top free agents at C
courtside move "brunson" PG      # plan a move (dry run, prints the payload)
courtside add 1234567 --drop "giddey"
courtside add 1234567 --waiver --bid 7
courtside drop "giddey"
```

**Every write is a dry run** unless you pass `--execute` *and* set
`ESPN_WRITE_ENABLED=1`. A dry run prints the exact URL and JSON body that would
be sent.

`move` works like ESPN's own "MOVE" button. If the target slot is full it swaps
with the occupant when that's legal, and otherwise benches the occupant.

## Verifying payloads against your league

The payload shapes come from public projects that captured them in a browser.
Before turning on writes, capture one real request of each kind from your league
and check it:

```bash
courtside compare captured.json
# OK: our ROSTER builder matches the capture exactly
```

See [docs/CAPTURE.md](docs/CAPTURE.md) for how to capture a request.

## HTTP API (`server/`)

A FastAPI app over the same client, deployed on Vercel, for the Android app.

| Route | |
|---|---|
| `GET /context` | Your team, today's scoring period, current matchup week |
| `GET /league` | Settings and standings |
| `GET /roster?day=`, `GET /teams/{id}?day=` | Roster with fantasy-point averages and each player's NBA game that day |
| `GET /scoreboard?week=` | Matchups with live points |
| `GET /players?q=&pos=&available=` | Free agents, or search all players |
| `GET /activity`, `GET /pending` | League transactions, pending claims and trades |
| `POST /lineup/preview` → `/lineup/confirm` | Lineup moves |
| `POST /roster/preview` → `/roster/confirm` | Add, drop, waiver claim |

Send `Authorization: Bearer <token>`. A Supabase Auth access token for an
email on `COURTSIDE_ALLOWED_EMAILS` can read and write; `COURTSIDE_API_KEY`
can only read. A confirm re-plans against fresh ESPN data and answers 409 if
the plan changed since the preview. Server env: the `ESPN_*` settings,
`COURTSIDE_API_KEY`, `SUPABASE_URL`, `COURTSIDE_ALLOWED_EMAILS`.

## Layout

| Module | What it does |
|---|---|
| `transactions.py` | Pure payload builders, lineup move planner, capture diff. No network. |
| `client.py` | Reads (`lm-api-reads`) and writes (`lm-api-writes`), with dry-run gating. |
| `models.py` | `Team` / `Player` views over ESPN's JSON. |
| `slots.py` | Lineup slot ids (PG=0 … UTIL=11, BE=12, IR=13). |
| `cli.py` | `courtside` command. |

## Tests

```bash
pytest
```

The suite runs fully offline against a fake ESPN backend (`tests/conftest.py`).

## Status

| Feature | State |
|---|---|
| Roster, free agents, scoring period | Built; read endpoints are well established (used by `espn-api`). |
| Lineup moves | Built; payload verified against a live capture (Oct 2026). |
| Free-agent add/drop | Built; payload verified against a live capture (Oct 2026). |
| Waiver claims + FAAB | Built; `bidAmount` placement unverified. |
| Trades | Not started. Accept/decline has never been publicly captured. |
