"""`just slot`: its decisions, on plain text, with no Docker and no worktree.

The shell around them (`git worktree`, `supabase start`) runs for real when a slot is
created.
"""

import subprocess
import tomllib
from pathlib import Path

import pytest
from slot import (
    EXCLUDED_SERVICES,
    SlotError,
    config_problems,
    main,
    removal_problems,
    slot_config,
    slot_number,
)

ROOT = Path(__file__).resolve().parent.parent

# The shape of supabase/config.toml: Twochi's ports are the 553xx ones; the others stay.
MAIN = """\
# A string used to distinguish different Supabase projects on the same host.
project_id = "twochi"

[api]
enabled = true
port = 55321
max_rows = 1000

[db]
port = 55322
shadow_port = 55320
major_version = 17

[db.pooler]
enabled = false
port = 55329

[studio]
port = 55323
api_url = "http://127.0.0.1"

[local_smtp]
port = 55324
# Uncomment to expose additional ports for testing user applications that send emails.
# smtp_port = 54325
# pop3_port = 54326

[auth]
site_url = "http://127.0.0.1:5173"

[auth.third_party.firebase]
enabled = false
# project_id = "my-firebase-project"

[edge_runtime]
inspector_port = 8083

[analytics]
port = 55327
"""


def changed_lines(before: str, after: str) -> dict[str, str]:
    lines = zip(before.splitlines(True), after.splitlines(True), strict=True)
    return {old.rstrip("\n"): new.rstrip("\n") for old, new in lines if old != new}


def test_a_slot_gets_its_own_project_and_ports_and_nothing_else_changes() -> None:
    assert changed_lines(MAIN, slot_config(MAIN, 1)) == {
        'project_id = "twochi"': 'project_id = "twochi-s1"',
        "port = 55321": "port = 55421",
        "port = 55322": "port = 55422",
        "shadow_port = 55320": "shadow_port = 55420",
        "port = 55329": "port = 55429",
        "port = 55323": "port = 55423",
        "port = 55324": "port = 55424",
        "port = 55327": "port = 55427",
    }


@pytest.mark.parametrize("slot", [2, 3, 9])
def test_each_slot_is_a_hundred_ports_further(slot: int) -> None:
    config = tomllib.loads(slot_config(MAIN, slot))

    assert config["project_id"] == f"twochi-s{slot}"
    assert config["db"]["port"] == 55322 + 100 * slot
    assert config["api"]["port"] == 55321 + 100 * slot


def test_a_twochi_port_inside_a_url_moves_too() -> None:
    # Left behind, the slot's Auth would send people to the main folder's instance.
    config = MAIN.replace('"http://127.0.0.1"', '"http://127.0.0.1:55321"')

    assert 'api_url = "http://127.0.0.1:55521"' in slot_config(config, 2)


# --- The pre-commit guard -------------------------------------------------------------


def test_the_main_folders_config_may_be_committed() -> None:
    assert config_problems(MAIN) == []


@pytest.mark.parametrize("slot", [1, 2, 9])
def test_a_slots_config_may_not_be_committed(slot: int) -> None:
    problems = config_problems(slot_config(MAIN, slot))

    assert f"twochi-s{slot}" in problems[0]
    assert str(55322 + 100 * slot) in " ".join(problems)


def test_a_slots_project_on_the_main_ports_is_refused() -> None:
    assert len(config_problems(MAIN.replace('"twochi"', '"twochi-s1"', 1))) == 1


def test_a_slots_ports_under_the_main_project_are_refused_one_by_one() -> None:
    by_hand = slot_config(MAIN, 1).replace('"twochi-s1"', '"twochi"')

    problems = config_problems(by_hand)

    assert len(problems) == 7
    assert "line 6" in problems[0]
    assert "55421" in problems[0]


def test_a_config_that_is_not_toml_is_refused() -> None:
    assert config_problems("project_id = twochi") != []


def test_a_slots_config_is_never_rewritten_again() -> None:
    with pytest.raises(SlotError):
        slot_config(slot_config(MAIN, 1), 2)


def test_the_guard_names_the_file_it_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mains = tmp_path / "main.toml"
    mains.write_text(MAIN, encoding="utf-8")
    slots = tmp_path / "slot.toml"
    slots.write_text(slot_config(MAIN, 2), encoding="utf-8")

    assert main(["guard", str(mains)]) == 0
    assert main(["guard", str(mains), str(slots)]) == 1
    errors = capsys.readouterr().err
    assert str(slots) in errors
    assert str(mains) not in errors


def test_the_config_git_holds_is_the_main_folders() -> None:
    # The tests follow whatever port the config names, so CI would pass on a slot's
    # config; the pre-commit guard is local and can be skipped. In a slot the file on
    # disk is rewritten on purpose: what counts is what git holds.
    held = subprocess.run(
        ["git", "show", "HEAD:supabase/config.toml"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout

    assert config_problems(held) == []


# --- Which slot, and when it may go ---------------------------------------------------


def test_a_slot_is_a_number_from_one_to_nine() -> None:
    assert [slot_number(raw) for raw in ("1", "3", "9")] == [1, 3, 9]


@pytest.mark.parametrize("raw", ["0", "", "-1", "1.5", "one", "10", "00", "twochi"])
def test_the_main_folder_and_anything_else_is_no_slot(raw: str) -> None:
    with pytest.raises(SlotError):
        slot_number(raw)


@pytest.fixture
def no_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fails the test if anything is run: a refusal must come before git and Docker."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"ran {args}")

    monkeypatch.setattr(subprocess, "run", refuse)


@pytest.mark.parametrize(
    "command",
    [
        ["down", "0"],
        ["down", "0", "--force"],
        ["down", "twochi"],
        ["down", ""],
        ["up", "0", "two-0-some-branch"],
    ],
)
@pytest.mark.usefixtures("no_commands")
def test_slot_zero_is_refused_before_anything_runs(
    command: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(command) == 1
    assert "main folder" in capsys.readouterr().err


@pytest.mark.usefixtures("no_commands")
def test_a_missing_slot_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["down"])

    assert stopped.value.code == 2


def test_a_slot_starts_the_services_ci_starts() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert f"supabase start -x {EXCLUDED_SERVICES}\n" in ci


def test_a_clean_and_pushed_worktree_may_be_removed() -> None:
    assert removal_problems(status="", unpushed="") == []


def test_uncommitted_changes_keep_the_worktree() -> None:
    problems = removal_problems(status=" M justfile\n?? notes.md\n", unpushed="")

    assert len(problems) == 1
    assert "2 uncommitted" in problems[0]


def test_unpushed_commits_keep_the_worktree() -> None:
    problems = removal_problems(status="", unpushed="d23ce60 one\n3ac9c90 two\n")

    assert len(problems) == 1
    assert "2 unpushed" in problems[0]
