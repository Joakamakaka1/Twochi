"""`just check-pr-body`: a draft body judged as CI's `flujo` judges the PR (TWO-26).

Each test builds a throwaway git repository with a base branch and a PR branch on top,
so the changed files come from `git diff`, as they do in CI.
"""

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


def git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603 - git with this test's own arguments
        ["git", *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
    )


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
    """A repository on branch `feature`, one commit ahead of `main`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    commit(repo, {"README.md": "base\n", **base}, "chore: base")
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


def test_main_rejects_a_missing_body_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check_pr_body.py", str(tmp_path / "missing.md")]) == 2

    assert "missing.md" in capsys.readouterr().err


def test_main_needs_the_body_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check_pr_body.py"]) == 2

    assert "usage" in capsys.readouterr().err
