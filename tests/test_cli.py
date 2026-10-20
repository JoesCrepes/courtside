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
