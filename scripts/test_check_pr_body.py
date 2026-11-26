"""`just check-pr-body`: a draft body judged as CI's `flujo` judges the PR (TWO-26).

Each test builds a throwaway git repository with a base branch and a PR branch on top,
so the changed files come from `git diff`, as they do in CI.
"""

import os
import subprocess
from pathlib import Path

import pytest
from check_pr_body import main, run

ROOT = Path(__file__).resolve().parent.parent
FLUJO = (ROOT / ".github" / "scripts" / "flujo.py").read_text(encoding="utf-8")
FLUJO_PATH = ".github/scripts/flujo.py"
TESTDATA = Path(__file__).parent / "testdata"

# PR 13, as `gh pr view 13 --json title,files` gives it.
PR13_TITLE = (
    "feat(infra): serve index.html for PWA deep links with a CloudFront Function "
    "(TWO-21)"
)
PR13_FILES = (
    ".github/workflows/ci.yml",
    "infra/stack/README.md",
    "infra/stack/edge.tf",
    "infra/stack/functions/web_routes.js",
    "infra/stack/functions/web_routes.test.mjs",
    "justfile",
)
STUB_FLUJO = 'print("stub flujo")\n'

# What git exports to a hook (GIT_DIR and its kin). Under the pre-push hook they would
# point this test's `git init` and `git config` at the real repository.
LOCAL_GIT_VARIABLES = frozenset(
    subprocess.run(
        ["git", "rev-parse", "--local-env-vars"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 - git with this test's own arguments
        ["git", *args],  # noqa: S607
        cwd=repo,
        env={k: v for k, v in os.environ.items() if k not in LOCAL_GIT_VARIABLES},
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit(repo: Path, files: dict[str, str], subject: str) -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "--message", subject)


def make_repo(
    tmp_path: Path,
    *,
    base: dict[str, str],
    branch: dict[str, str],
    subject: str = PR13_TITLE,
) -> Path:
    """A repository on branch `feature`, one commit ahead of `main`, as in `origin`."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(origin))
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    commit(repo, {"README.md": "base\n", **base}, "chore: base")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "--quiet", "origin", "main")
    git(repo, "switch", "--quiet", "--create", "feature")
    commit(repo, branch, subject)
    return repo


def pr13_repo(tmp_path: Path) -> Path:
    return make_repo(
        tmp_path,
        base={FLUJO_PATH: FLUJO},
        branch={path: "changed\n" for path in PR13_FILES},
    )


def check_body(
    repo: Path, tmp_path: Path, body: str, title: str | None = PR13_TITLE
) -> int:
    body_path = tmp_path / "body.md"
    body_path.write_text(body, encoding="utf-8")
    return run(body_path, title, base="main", repo=repo)


def test_pr13_original_body_fails_for_its_missing_sections(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = pr13_repo(tmp_path)
    body = (TESTDATA / "pr13_body_original.md").read_text(encoding="utf-8")

    assert check_body(repo, tmp_path, body) == 1

    out = capsys.readouterr().out
    for section in ("Tamaño", "Revisión", "Evidencia", "Peligro de fusión"):
        assert f"«{section}»" in out
    assert "::error title=flujo::" in out


def test_pr13_final_body_with_size_and_review_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = pr13_repo(tmp_path)
    body = (TESTDATA / "pr13_body_final.md").read_text(encoding="utf-8")

    assert check_body(repo, tmp_path, body) == 0

    out = capsys.readouterr().out
    assert "flujo: OK" in out
    assert "::error" not in out


def test_title_defaults_to_the_last_commit_subject(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        base={FLUJO_PATH: FLUJO},
        branch={"docs/notes.md": "x\n"},
        subject="Add some notes",
    )

    assert check_body(repo, tmp_path, "", title=None) == 1

    out = capsys.readouterr().out
    assert "Add some notes" in out
    assert "Conventional Commits" in out


def test_a_renamed_sensitive_path_counts_as_ci_counts_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        base={FLUJO_PATH: FLUJO, "infra/stack/old.tf": "same\n"},
        branch={"docs/new.md": "x\n"},
        subject="docs: add a note",
    )
    git(repo, "mv", "infra/stack/old.tf", "docs/old.tf")
    git(repo, "commit", "--quiet", "--message", "docs: move a note")

    assert check_body(repo, tmp_path, "", title="docs: move a note") == 1

    assert "infra/stack/old.tf" in capsys.readouterr().out


def test_runs_the_base_copy_of_flujo_as_ci_does(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        base={FLUJO_PATH: STUB_FLUJO},
        branch={FLUJO_PATH: FLUJO, "infra/main.tf": "x\n"},
    )

    assert check_body(repo, tmp_path, "") == 0

    assert "stub flujo" in capsys.readouterr().out


def test_runs_the_branch_copy_while_the_base_has_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, base={}, branch={FLUJO_PATH: STUB_FLUJO})

    assert check_body(repo, tmp_path, "") == 0

    assert "stub flujo" in capsys.readouterr().out


def test_git_inside_a_hook_stays_in_its_own_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # What git exports to the pre-push hook that runs `just check`.
    decoy = tmp_path / "decoy.git"
    monkeypatch.setenv("GIT_DIR", str(decoy))
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / "index"))
    repo = pr13_repo(tmp_path)
    body = (TESTDATA / "pr13_body_final.md").read_text(encoding="utf-8")

    assert check_body(repo, tmp_path, body) == 0

    assert "flujo: OK" in capsys.readouterr().out
    assert not decoy.exists()


# Review: fetch the base, stacked branches, merge commits.


def advance_origin_main(repo: Path, files: dict[str, str]) -> None:
    """A new commit on origin's main that the local origin/main does not know yet."""
    known = git(repo, "rev-parse", "origin/main")
    git(repo, "switch", "--quiet", "--create", "upstream", "origin/main")
    commit(repo, files, "chore: upstream")
    git(repo, "push", "--quiet", "origin", "upstream:main")
    git(repo, "update-ref", "refs/remotes/origin/main", known)
    git(repo, "switch", "--quiet", "feature")


def test_fetches_the_base_before_judging(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, base={FLUJO_PATH: FLUJO}, branch={"docs/a.md": "x\n"})
    advance_origin_main(repo, {FLUJO_PATH: STUB_FLUJO})

    assert check_body(repo, tmp_path, "") == 0

    assert "stub flujo" in capsys.readouterr().out


def test_a_failed_fetch_warns_and_judges_the_known_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = pr13_repo(tmp_path)
    git(repo, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    body = (TESTDATA / "pr13_body_final.md").read_text(encoding="utf-8")

    assert check_body(repo, tmp_path, body) == 0

    captured = capsys.readouterr()
    assert "flujo: OK" in captured.out
    assert "could not fetch origin/main" in captured.err
    assert "stale" in captured.err


def test_a_stacked_branch_is_judged_against_its_own_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        base={FLUJO_PATH: FLUJO},
        branch={"infra/main.tf": "x\n"},
        subject="feat(infra): lower slice (TWO-1)",
    )
    git(repo, "push", "--quiet", "origin", "feature:lower")
    commit(repo, {"docs/upper.md": "x\n"}, "docs: upper slice (TWO-2)")
    body = tmp_path / "body.md"
    body.write_text("## Tamaño\n\nTrivial.\n", encoding="utf-8")
    argv = ["check_pr_body.py", str(body), "docs: upper slice (TWO-2)"]

    assert main([*argv, "--base", "lower"], repo=repo) == 0
    assert main(argv, repo=repo) == 1

    out = capsys.readouterr().out
    assert "infra/main.tf" in out


def test_default_title_skips_merge_commits(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path, base={FLUJO_PATH: FLUJO}, branch={"docs/a.md": "x\n"})
    # main's commit is newer than the branch's, as after any `merge origin/main`.
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2090-01-01T00:00:00+00:00")
    advance_origin_main(repo, {"docs/b.md": "y\n"})
    monkeypatch.delenv("GIT_COMMITTER_DATE")
    git(repo, "fetch", "--quiet", "origin")
    git(repo, "merge", "--quiet", "--no-ff", "--no-edit", "origin/main")

    check_body(repo, tmp_path, "", title=None)

    assert f"Title: {PR13_TITLE}\n" in capsys.readouterr().out


def test_main_rejects_a_missing_body_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check_pr_body.py", str(tmp_path / "missing.md")]) == 2

    assert "missing.md" in capsys.readouterr().err


def test_main_needs_the_body_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check_pr_body.py"]) == 2

    assert "usage" in capsys.readouterr().err
