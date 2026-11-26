"""`just slot`: its decisions, on plain text, with no Docker and no worktree.

The shell around them (`git worktree`, `supabase start`) runs for real when a slot is
created.
"""

import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import cast

import pytest
import slot
from conftest import database_urls
from git_env import git_environment
from slot import (
    EXCLUDED_SERVICES,
    SlotError,
    checkout_problems,
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


# --- A slot keeps its own config ------------------------------------------------------

MAIN_FOLDER = Path("/dev/twochi")
SLOT_2 = MAIN_FOLDER / ".claude" / "worktrees" / "slot-2"


def test_a_slot_on_its_own_config_has_no_problem() -> None:
    assert checkout_problems(SLOT_2, slot_config(MAIN, 2)) == []


def test_a_slot_back_on_the_main_folders_config_is_a_problem() -> None:
    # What clearing skip-worktree, a checkout or a merge leaves behind.
    problems = checkout_problems(SLOT_2, MAIN)

    assert 'project_id is "twochi", not "twochi-s2"' in problems[0]
    assert "55322" in " ".join(problems)


def test_a_slot_on_another_slots_config_is_a_problem() -> None:
    assert checkout_problems(SLOT_2, slot_config(MAIN, 1)) != []


def test_a_slots_project_on_other_ports_is_a_problem_port_by_port() -> None:
    by_hand = MAIN.replace('"twochi"', '"twochi-s2"', 1)

    assert len(checkout_problems(SLOT_2, by_hand)) == 7


def test_a_slot_whose_config_is_not_toml_is_a_problem() -> None:
    assert checkout_problems(SLOT_2, "project_id = twochi-s2") != []


@pytest.mark.parametrize(
    "folder",
    [
        MAIN_FOLDER,
        MAIN_FOLDER / ".claude" / "worktrees" / "youthful-lichterman-56d803",
        MAIN_FOLDER / ".claude" / "worktrees" / "slot-0",
        Path("/elsewhere/slot-2"),
    ],
)
def test_a_folder_that_is_no_slot_is_not_judged(folder: Path) -> None:
    assert checkout_problems(folder, MAIN) == []
    assert checkout_problems(folder, slot_config(MAIN, 3)) == []


def checkout_at(folder: Path, config: str) -> Path:
    (folder / "supabase").mkdir(parents=True)
    (folder / "supabase" / "config.toml").write_text(config, encoding="utf-8")
    return folder


def test_the_check_command_refuses_a_slot_on_the_main_folders_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lost = checkout_at(tmp_path / "a" / ".claude" / "worktrees" / "slot-2", MAIN)

    assert main(["check", str(lost)]) == 1
    assert "twochi-s2" in capsys.readouterr().err


def test_the_check_command_passes_a_slot_on_its_config_and_the_main_folder(
    tmp_path: Path,
) -> None:
    slot = tmp_path / "b" / ".claude" / "worktrees" / "slot-2"

    assert main(["check", str(checkout_at(slot, slot_config(MAIN, 2)))]) == 0
    assert main(["check", str(checkout_at(tmp_path / "c", MAIN))]) == 0


# --- The database the tests reach -----------------------------------------------------

ELSEWHERE = {
    "TWOCHI_TEST_ADMIN_URL": "postgresql://postgres:other@db.twochi.test/postgres",
    "TWOCHI_TEST_DATABASE_URL": "postgresql://twochi_api:other@db.twochi.test/postgres",
    "TWOCHI_TEST_BACKUP_URL": "postgresql://twochi_backup:other@db.twochi.test/postgres",
}


def test_in_a_slot_the_tests_reach_the_slots_database() -> None:
    urls = database_urls(SLOT_2, slot_config(MAIN, 2), env={})

    assert urls.admin == "postgresql://postgres:postgres@127.0.0.1:55522/postgres"
    assert urls.api == (
        "postgresql://twochi_api:twochi-api-local@127.0.0.1:55522/postgres"
    )
    assert urls.backup == (
        "postgresql://twochi_backup:twochi-backup-local@127.0.0.1:55522/postgres"
    )


def test_in_the_main_folder_the_tests_reach_twochis_database() -> None:
    urls = database_urls(MAIN_FOLDER, MAIN, env={})

    assert urls.admin == "postgresql://postgres:postgres@127.0.0.1:55322/postgres"


def test_each_variable_still_overrides_its_url() -> None:
    api = ELSEWHERE["TWOCHI_TEST_DATABASE_URL"]

    urls = database_urls(MAIN_FOLDER, MAIN, env={"TWOCHI_TEST_DATABASE_URL": api})

    assert urls.api == api
    assert urls.admin == "postgresql://postgres:postgres@127.0.0.1:55322/postgres"


def test_a_slot_on_the_main_folders_config_reaches_no_database() -> None:
    # Its tests would write to the main folder's database.
    with pytest.raises(SlotError, match="slot 2"):
        database_urls(SLOT_2, MAIN, env={})


def test_one_variable_does_not_excuse_a_slot_on_the_main_folders_config() -> None:
    api = ELSEWHERE["TWOCHI_TEST_DATABASE_URL"]

    with pytest.raises(SlotError):
        database_urls(SLOT_2, MAIN, env={"TWOCHI_TEST_DATABASE_URL": api})


def test_the_three_variables_say_where_and_the_config_is_not_judged() -> None:
    urls = database_urls(SLOT_2, MAIN, env=ELSEWHERE)

    assert [urls.admin, urls.api, urls.backup] == list(ELSEWHERE.values())


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
    # And `just slot` can still rewrite it: a drift of the real file breaks here.
    assert tomllib.loads(slot_config(held, 1))["db"]["port"] == 55422


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


def removal(
    *,
    status: str = "",
    unpushed: str = "",
    config: str | None = None,
    held: str = MAIN,
) -> list[str]:
    """What keeps slot 2's worktree; by default clean, pushed and on its config."""
    return removal_problems(
        slot=2,
        status=status,
        unpushed=unpushed,
        config=slot_config(MAIN, 2) if config is None else config,
        held=held,
    )


def test_a_clean_and_pushed_worktree_may_be_removed() -> None:
    assert removal() == []


def test_uncommitted_changes_keep_the_worktree() -> None:
    problems = removal(status=" M justfile\n?? notes.md\n")

    assert len(problems) == 1
    assert "2 uncommitted" in problems[0]


def test_unpushed_commits_keep_the_worktree() -> None:
    problems = removal(unpushed="d23ce60 one\n3ac9c90 two\n")

    assert len(problems) == 1
    assert "2 unpushed" in problems[0]


def test_an_edit_of_the_slots_config_keeps_the_worktree() -> None:
    # skip-worktree hides it: `git status` is clean, and the edit would go unseen.
    edited = slot_config(MAIN, 2).replace("max_rows = 1000", "max_rows = 50")

    problems = removal(config=edited)

    assert len(problems) == 1
    assert "hidden from `git status`" in problems[0]


def test_a_slot_back_on_the_main_folders_config_keeps_the_worktree() -> None:
    assert len(removal(config=MAIN)) == 1


def test_a_config_in_git_that_no_slot_can_run_keeps_the_worktree() -> None:
    # Nothing to compare the file with: it may hold an edit.
    assert len(removal(held=slot_config(MAIN, 1))) == 1


# --- A slot does not remove itself ----------------------------------------------------


@pytest.mark.parametrize("command", [["down", "2"], ["down", "2", "--force"]])
@pytest.mark.usefixtures("no_commands")
def test_a_slot_is_not_removed_from_its_own_checkout(
    command: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    # On Windows its own Python is in use: Supabase would go and the folder stay.
    assert main(command, checkout=SLOT_2) == 1
    assert "main folder" in capsys.readouterr().err


@pytest.mark.usefixtures("no_commands")
def test_a_slot_is_not_removed_from_a_folder_inside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inside = tmp_path / ".claude" / "worktrees" / "slot-2" / "packages"
    inside.mkdir(parents=True)
    monkeypatch.chdir(inside)

    assert main(["down", "2"], checkout=MAIN_FOLDER) == 1


# --- Removing a slot, with real git on a throwaway repository -------------------------


# The tests below replace `subprocess.run`; their own git keeps the real one.
RUN = subprocess.run


def git(repo: Path, *args: str) -> str:
    return RUN(
        ["git", *args],
        cwd=repo,
        env=git_environment(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A main folder with slot 2 on a clean, pushed branch and on the slot's config."""
    git(tmp_path, "init", "--quiet", "--initial-branch=main", "repo")
    repo = (tmp_path / "repo").resolve()
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    checkout_at(repo, MAIN)
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "--message", "chore: first")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    folder = repo / ".claude" / "worktrees" / "slot-2"
    git(repo, "worktree", "add", "--quiet", "-b", "two-2-x", str(folder))
    (folder / "supabase" / "config.toml").write_bytes(
        slot_config(MAIN, 2).encode("utf-8")
    )
    git(folder, "update-index", "--skip-worktree", "supabase/config.toml")
    (folder / "node_modules" / ".pnpm").mkdir(parents=True)
    monkeypatch.setattr(slot, "_main_folder", lambda: repo)
    return repo


def slot_2(repo: Path) -> Path:
    return repo / ".claude" / "worktrees" / "slot-2"


def listed(repo: Path) -> bool:
    return f"worktree {slot_2(repo).as_posix()}\n" in git(
        repo, "worktree", "list", "--porcelain"
    )


def leave_leftovers(repo: Path) -> None:
    """What Git for Windows leaves when a process holds a file of the worktree open."""
    git(repo, "worktree", "remove", "--force", str(slot_2(repo)))
    held = slot_2(repo) / "node_modules" / ".pnpm" / "held.txt"
    held.parent.mkdir(parents=True)
    held.write_text("x", encoding="utf-8")


@pytest.fixture
def windows_git(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Real git, except `git worktree remove`, which fails as on Windows with a file
    held open: the worktree is no longer listed and its folder stays. Supabase is
    not run. Returns the commands that ran, by name."""
    ran: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        named = [Path(args[0]).stem, *args[1:]]
        ran.append(named)
        if named[0] == "supabase":
            return subprocess.CompletedProcess(args, 0)
        if named[1:3] == ["worktree", "remove"]:
            cwd = cast(Path, kwargs["cwd"])
            leave_leftovers(cwd)
            return subprocess.CompletedProcess(args, 255)
        return RUN(args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", run)
    return ran


def test_a_removal_that_fails_after_git_drops_the_worktree_removes_the_rest(
    repo: Path, windows_git: list[list[str]]
) -> None:
    assert main(["down", "2"], checkout=repo) == 0

    assert not slot_2(repo).exists()
    assert not listed(repo)
    assert ["git", "worktree", "prune"] in windows_git


def test_slot_down_on_the_leftovers_removes_them(
    repo: Path, windows_git: list[list[str]]
) -> None:
    leave_leftovers(repo)

    assert main(["down", "2"], checkout=repo) == 0

    assert not slot_2(repo).exists()
    assert ["git", "worktree", "prune"] in windows_git


def test_a_removal_that_fails_with_the_worktree_still_listed_keeps_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if Path(args[0]).stem == "supabase" or args[1:3] == ["worktree", "remove"]:
            code = 0 if Path(args[0]).stem == "supabase" else 128
            return subprocess.CompletedProcess(args, code)
        return RUN(args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", run)

    assert main(["down", "2"], checkout=repo) == 1

    assert slot_2(repo).is_dir()
    assert listed(repo)
    assert "worktree remove" in capsys.readouterr().err


def test_leftovers_still_in_use_say_to_run_it_again(
    repo: Path,
    windows_git: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def in_use(path: Path) -> None:
        raise PermissionError(f"[WinError 32] in use: '{path}'")

    monkeypatch.setattr(shutil, "rmtree", in_use)

    assert main(["down", "2"], checkout=repo) == 1

    assert not listed(repo)
    assert "`just slot-down 2` again" in capsys.readouterr().err


def test_a_hooks_git_variables_do_not_reach_a_slots_git(
    repo: Path, windows_git: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Under the pre-push hook they would point git at the repository being pushed.
    monkeypatch.setenv("GIT_DIR", str(repo.parent / "elsewhere" / ".git"))

    assert main(["down", "2"], checkout=repo) == 0

    monkeypatch.delenv("GIT_DIR")
    assert not slot_2(repo).exists()
    assert not listed(repo)


def test_dependencies_are_copies_and_no_links_to_a_shared_store() -> None:
    # On Windows no link of a loaded .pyd or .node can be deleted: a link would keep a
    # slot's .venv or node_modules while any other checkout has that module loaded.
    uv = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert uv["tool"]["uv"]["link-mode"] == "copy"
    workspace = (ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    assert "packageImportMethod: copy" in workspace.splitlines()


def test_a_folder_with_its_own_git_is_not_taken_for_leftovers(
    repo: Path, windows_git: list[list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    # What a failed removal leaves has no `.git`; a clone in its place may hold work.
    leave_leftovers(repo)
    git(slot_2(repo), "init", "--quiet")

    assert main(["down", "2"], checkout=repo) == 1

    assert (slot_2(repo) / ".git").is_dir()
    assert "remove it by hand" in capsys.readouterr().err
    assert not any(named[0] == "supabase" for named in windows_git)
