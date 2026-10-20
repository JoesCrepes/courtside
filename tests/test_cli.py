import json
from pathlib import Path

import pytest

from courtside import cli

from conftest import LEAGUE_ID, SEASON, SWID, TEAM_ID

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no stray .env
    monkeypatch.setenv("ESPN_LEAGUE_ID", str(LEAGUE_ID))
    monkeypatch.setenv("ESPN_SEASON", str(SEASON))
    monkeypatch.setenv("ESPN_TEAM_ID", str(TEAM_ID))
    monkeypatch.setenv("ESPN_S2", "AEfakeS2cookie")
    monkeypatch.setenv("ESPN_SWID", SWID.strip("{}"))  # braces get added back
    monkeypatch.delenv("ESPN_WRITE_ENABLED", raising=False)


def test_compare_ok(capsys):
    assert cli.main(["compare", str(FIXTURES / "captured_lineup.json")]) == 0
    assert "OK: our ROSTER builder matches" in capsys.readouterr().out


def test_compare_mismatch(tmp_path, capsys):
    captured = json.loads((FIXTURES / "captured_freeagent.json").read_text())
    captured["items"][0]["fromTeamId"] = 0  # pretend ESPN also sends this
    f = tmp_path / "c.json"
    f.write_text(json.dumps(captured))
    assert cli.main(["compare", str(f)]) == 1
    assert "missing in ours: items[0].fromTeamId" in capsys.readouterr().out


def test_roster_command(env, fake, capsys):
    assert cli.main(["roster"]) == 0
    out = capsys.readouterr().out
    assert "Joe's Crepes (JOE)" in out
    lines = out.splitlines()
    # Starters print before the bench, and IR last.
    assert lines[1].split()[0] == "PG"
    assert "Injured Ivan" in lines[-1] and "[OUT]" in lines[-1]


def test_fa_command(env, fake, capsys):
    assert cli.main(["fa", "--limit", "5"]) == 0
    out = capsys.readouterr().out
    assert "42.5%" in out and "Free Fred" in out
    assert "WA  Waiver Will" in out and "WA  Free Fred" not in out


def test_move_command_is_dry_run_even_with_execute(env, fake, capsys):
    # ESPN_WRITE_ENABLED is unset, so --execute alone must not POST.
    assert cli.main(["move", "bench ben", "PG", "--execute"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
    assert fake.posts == []


def test_move_command_executes_when_enabled(env, fake, monkeypatch, capsys):
    monkeypatch.setenv("ESPN_WRITE_ENABLED", "1")
    assert cli.main(["move", "bench ben", "PG", "--execute"]) == 0
    assert len(fake.posts) == 1
    assert fake.posts[0]["memberId"] == SWID


def test_add_with_drop_by_name(env, fake, capsys):
    assert cli.main(["add", "201", "--drop", "bigs"]) == 0
    payload = json.loads(capsys.readouterr().out)["payload"]
    assert [(i["type"], i["playerId"]) for i in payload["items"]] == [("ADD", 201), ("DROP", 110)]


def test_bad_move_is_friendly_error(env, fake, capsys):
    assert cli.main(["move", "center cal", "PG"]) == 1
    assert "not eligible for PG" in capsys.readouterr().err


def test_compare_accepts_byte_order_mark(tmp_path, capsys):
    f = tmp_path / "bom.json"
    f.write_text((FIXTURES / "captured_lineup.json").read_text(), encoding="utf-8-sig")
    assert cli.main(["compare", str(f)]) == 0


def test_compare_bad_input_is_friendly_error(tmp_path, capsys):
    f = tmp_path / "trade.json"
    f.write_text('{"teamId": 3, "type": "TRADE_PROPOSAL", "items": []}')
    assert cli.main(["compare", str(f)]) == 1
    assert "no builder for transaction type" in capsys.readouterr().err
    assert cli.main(["compare", str(tmp_path / "missing.json")]) == 1


def test_dotenv_with_byte_order_mark(env, monkeypatch):
    from courtside import Config

    monkeypatch.delenv("ESPN_LEAGUE_ID")
    (Path.cwd() / ".env").write_text("ESPN_LEAGUE_ID=42\n", encoding="utf-8-sig")
    assert Config.from_env().league_id == 42


def test_non_ascii_names_survive_a_cp1252_pipe(tmp_path):
    import subprocess
    import sys

    script = (
        "import sys, io\n"
        "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='cp1252')\n"
        "from courtside import cli\n"
        "cli.main(['compare', 'nope.json'])\n"
        "print('Nikola Joki\u0107')\n"
    )
    r = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True)
    assert r.returncode == 0, r.stderr
    assert "Jokić" in r.stdout.decode("utf-8")


def test_compare_reads_har_exports(tmp_path, capsys):
    body = (FIXTURES / "captured_lineup.json").read_text()
    har = {"log": {"entries": [
        {"request": {"method": "GET", "url": "https://lm-api-reads.fantasy.espn.com/x"}},
        {"request": {"method": "POST", "url": "https://lm-api-writes.fantasy.espn.com/x/transactions/?v=1",
                     "postData": {"text": body}}},
    ]}}
    f = tmp_path / "x.har"
    f.write_text(json.dumps(har))
    assert cli.main(["compare", str(f)]) == 0
    assert "OK: our ROSTER builder" in capsys.readouterr().out
