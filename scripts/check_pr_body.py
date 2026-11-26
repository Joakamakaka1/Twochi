"""`just check-pr-body`: a draft PR body judged as CI's `flujo` will judge it (TWO-26).

It hands `flujo` what the CI job hands it: the changed files as `git diff --name-only
--no-renames -z` writes them, against the PR's base, and an event file with the title
and the body. It runs the base's copy of flujo.py, as CI does, and this checkout's only
while the base has none. So neither flujo.py nor CI change.

The base is a branch on origin: main, or the branch below for a stacked PR (`--base`).
It is fetched first, so the verdict is against the base CI will see; without the
network the last fetched copy stands in, with a warning.

The title defaults to the subject of the last commit that is not a merge: commits
follow the same convention as the PR title, and `gh pr create --fill` takes it from
there on a one-commit branch. The branch name never fits the convention, so it would
always fail. Pass the PR's real title when it differs.

Usage: python check_pr_body.py BODY_FILE [TITLE] [--base BRANCH]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from git_env import git_environment

ROOT = Path(__file__).resolve().parent.parent
REMOTE = "origin"
BASE = "main"
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
        env=git_environment(),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args)}: {error}")
    return result.stdout


def _fetch(repo: Path, base: str) -> None:
    """Bring origin's base up to date; without it, warn and keep the last copy."""
    try:
        _git(repo, "fetch", "--quiet", REMOTE, base)
    except GitError as error:
        sys.stderr.write(
            f"Warning: could not fetch {REMOTE}/{base}, so the verdict may be against "
            f"a stale base ({error}).\n"
        )


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
        subject = _git(repo, "log", "-1", "--no-merges", "--format=%s")
        title = subject.decode("utf-8").strip()
    _fetch(repo, base)
    tracked = f"{REMOTE}/{base}"
    # The same diff as CI's, but from the merge base: the branch's own changes.
    changed = _git(
        repo, "diff", "--name-only", "--no-renames", "-z", f"{tracked}...HEAD"
    )
    flujo = _flujo_source(repo, tracked)
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


def main(argv: Sequence[str], *, repo: Path = ROOT) -> int:
    """`repo` is the checkout whose branch is judged: tests pass another."""
    parser = argparse.ArgumentParser(prog="check_pr_body.py")
    parser.add_argument("body", type=Path, help="the draft PR body, in Markdown")
    parser.add_argument("title", nargs="?", help="the PR title")
    parser.add_argument(
        "--base",
        default=BASE,
        help="the PR's base branch on origin: main, or the one below a stacked PR",
    )
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 2
    body_path: Path = args.body
    if not body_path.is_file():
        sys.stderr.write(f"No body file at {body_path}.\n")
        return 2
    try:
        return run(body_path, args.title, base=args.base, repo=repo)
    except GitError as error:
        sys.stderr.write(f"{error}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
