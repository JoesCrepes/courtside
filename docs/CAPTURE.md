# Capturing a real ESPN write request

ESPN doesn't document its write API, so the only ground truth is what your
browser sends. Capture one of each action you plan to use.

1. Open your team on fantasy.espn.com in Chrome or Firefox.
2. Open DevTools → **Network**, tick **Preserve log**, and filter by `transactions`.
3. Make the move on ESPN's site (swap two players, add a free agent, etc.).
4. Click the `POST .../transactions/` request → **Payload** → **view source**.
5. Copy the JSON into a file, e.g. `captures/lineup.json`. (`captures/` is gitignored.)
6. Run `courtside compare captures/lineup.json`.

Or skip steps 4-5: right-click the request list → **Save all as HAR**, save it
in `captures/`, and run `courtside compare captures/<file>.har`. Every
transaction in the HAR is checked. A HAR also holds your cookies, so keep it
out of git and delete it when you're done.

`compare` rebuilds the same action with our builders and diffs the result
against your capture. Values of `scoringPeriodId` and `memberId` are ignored,
but the keys must still be present. Any `missing in ours` or `extra in ours`
line means the builder in `src/courtside/transactions.py` needs updating.

Also note the response: ESPN's reply on success, and on a failed move such as a
locked player or a full roster, tells us what errors look like.

Things worth checking in your capture:

- Slot ids, especially if your league uses G/F/UTIL counts that aren't the default.
- Lineup items carry no `fromTeamId`/`toTeamId`; add/drop items do (both confirmed).
- Where `bidAmount` sits on a waiver claim.

The capture includes your `memberId` (SWID). Don't commit it.
