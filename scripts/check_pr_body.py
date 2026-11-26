"""`just check-pr-body`: a draft PR body judged as CI's `flujo` will judge it (TWO-26).

It hands `flujo` what the CI job hands it: the changed files as `git diff --name-only
--no-renames -z` writes them, here against origin/main, and an event file with the
title and the body. It runs origin/main's copy of flujo.py, as CI runs the base
branch's, and this checkout's only while the base has none. So neither flujo.py nor
CI change, and the verdict is CI's as long as origin/main is the PR's base.

The title defaults to the last commit's subject: commits follow the same convention as
the PR title, and `gh pr create --fill` takes it from there on a one-commit branch. The
branch name never fits the convention, so it would always fail. Pass the PR's real
title when it differs.

Usage: python check_pr_body.py BODY_FILE [TITLE]
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "origin/main"
FLUJO = ".github/scripts/flujo.py"
# Any login but Dependabot's: flujo exempts that one from the id and the sections.
AUTHOR = "local"


class GitError(Exception):
    """A git command failed; its message says which and why."""


def _git(repo: Path, *args: str) -> bytes:
    executable = shutil.which("git")
    if executable is None:
        raise GitError("git is not on PATH.")
    result = subprocess.run(  # noqa: S603 - git resolved on PATH, arguments built here
        [executable, "-c", "core.quotePath=false", *args],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args)}: {error}")
    return result.stdout


def _flujo_source(repo: Path, base: str) -> bytes:
    """The base's flujo.py, as CI runs it; this checkout's while the base has none."""
    try:
        return _git(repo, "show", f"{base}:{FLUJO}")
    except GitError:
        return (repo / FLUJO).read_bytes()


def run(
    body_path: Path, title: str | None, *, base: str = BASE, repo: Path = ROOT
) -> int:
    """Run `flujo` on the draft and print its verdict; its exit code is the result."""
    body = body_path.read_text(encoding="utf-8")
    if not title:
        title = _git(repo, "log", "-1", "--format=%s").decode("utf-8").strip()
    # The same diff as CI's, but from the merge base: the branch's own changes.
    changed = _git(repo, "diff", "--name-only", "--no-renames", "-z", f"{base}...HEAD")
    flujo = _flujo_source(repo, base)
    sys.stdout.write(f"Title: {title}\n")

    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        event = {
            "pull_request": {"title": title, "body": body, "user": {"login": AUTHOR}}
        }
        (folder / "event.json").write_text(json.dumps(event), encoding="utf-8")
        (folder / "changed.bin").write_bytes(changed)
        (folder / "flujo.py").write_bytes(flujo)
        result = subprocess.run(  # noqa: S603 - this interpreter on a file written here
            [
                sys.executable,
                "-X",
                "utf8",
                str(folder / "flujo.py"),
                str(folder / "changed.bin"),
            ],
            env=os.environ | {"GITHUB_EVENT_PATH": str(folder / "event.json")},
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        sys.stderr.write("usage: check_pr_body.py BODY_FILE [TITLE]\n")
        return 2
    body_path = Path(argv[1])
    if not body_path.is_file():
        sys.stderr.write(f"No body file at {body_path}.\n")
        return 2
    try:
        return run(body_path, argv[2] if len(argv) == 3 else None)
    except GitError as error:
        sys.stderr.write(f"{error}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
