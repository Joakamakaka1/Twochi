"""The pre-push guard: `just check` only on the tree that is pushed (TWO-26).

The decisions run on plain values; `main` runs once on a throwaway repository, on the
paths that refuse the push before `just check` starts.
"""

import os
import subprocess
from pathlib import Path

import pytest
from push_guard import main, push_problems

HEAD = "a" * 40
OTHER = "b" * 40
MAIN = Path("/work/twochi")
MAIN_CONFIG = 'project_id = "twochi"\n\n[db]\nport = 55322\n'
SLOT_3 = MAIN / ".claude" / "worktrees" / "slot-3"
SLOT_3_CONFIG = 'project_id = "twochi-s3"\n\n[db]\nport = 55622\n'
LOCAL_GIT_VARIABLES = frozenset(
    subprocess.run(
        ["git", "rev-parse", "--local-env-vars"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
)


def problems(
    *,
    checkout: Path = MAIN,
    pushed: str | None = HEAD,
    status: str = "",
    config: str = MAIN_CONFIG,
) -> list[str]:
    return push_problems(
        checkout=checkout,
        main_folder=MAIN,
        head=HEAD,
        pushed=pushed,
        status=status,
        config=config,
    )


def test_pushing_head_from_a_clean_main_folder_passes() -> None:
    assert problems() == []


def test_a_clean_slot_with_its_own_config_passes() -> None:
    assert problems(checkout=SLOT_3, config=SLOT_3_CONFIG) == []


def test_without_a_pushed_ref_the_checkout_is_judged() -> None:
    assert problems(pushed=None) == []


def test_pushing_another_ref_than_head_is_refused() -> None:
    found = problems(pushed=OTHER)
    assert len(found) == 1
    assert OTHER[:12] in found[0]
    assert HEAD[:12] in found[0]


@pytest.mark.parametrize("status", [" M justfile\n", "A  new.py\n", "?? notes.md\n"])
def test_a_tree_with_changes_is_refused(status: str) -> None:
    found = problems(status=status)
    assert len(found) == 1
    assert "uncommitted" in found[0]


def test_a_worktree_that_is_no_slot_with_the_main_config_is_refused() -> None:
    found = problems(checkout=MAIN / ".claude" / "worktrees" / "eager-turing")
    assert len(found) == 1
    assert "main folder's database" in found[0]


def test_a_worktree_that_is_no_slot_with_another_config_passes() -> None:
    other = 'project_id = "elsewhere"\n\n[db]\nport = 54322\n'
    checkout = MAIN / ".claude" / "worktrees" / "eager-turing"
    assert problems(checkout=checkout, config=other) == []


def test_a_slot_that_lost_its_config_is_refused() -> None:
    found = problems(checkout=SLOT_3, config=MAIN_CONFIG)
    assert found
    assert all("slot 3" in problem for problem in found)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 - git with this test's own arguments
        ["git", *args],  # noqa: S607
        cwd=repo,
        env={k: v for k, v in os.environ.items() if k not in LOCAL_GIT_VARIABLES},
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "--quiet", "--initial-branch=main", "repo")
    repo = tmp_path / "repo"
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "--message", "chore: first")
    git(repo, "switch", "--quiet", "--create", "other")
    git(repo, "commit", "--quiet", "--allow-empty", "--message", "chore: other")
    git(repo, "switch", "--quiet", "main")
    return repo


def test_main_refuses_a_push_of_another_branch(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PRE_COMMIT_TO_REF", git(repo, "rev-parse", "other"))

    assert main(checkout=repo) == 1

    err = capsys.readouterr().err
    assert "Push from that branch's worktree, with a clean tree." in err


def test_main_refuses_a_dirty_tree_under_a_hook(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # What git exports to a hook: the guard's git still reads `repo`.
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "decoy.git"))
    monkeypatch.setenv("PRE_COMMIT_TO_REF", git(repo, "rev-parse", "HEAD"))
    (repo / "wip.py").write_text("broken(\n", encoding="utf-8")

    assert main(checkout=repo) == 1

    assert "uncommitted" in capsys.readouterr().err
    assert not (tmp_path / "decoy.git").exists()
