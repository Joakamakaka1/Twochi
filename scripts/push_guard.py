"""The pre-push hook: `just check` on the tree that is pushed, and only there (TWO-26).

`just check` checks the checkout, not the pushed commits. So the hook refuses a push
whose commits are not the checkout's: another ref than HEAD (`git push origin
other-branch`), or a checkout with changes or untracked files. It also refuses a
worktree that is neither the main folder nor a slot but has the main folder's
supabase/config.toml: its `check-dump` would reset the main folder's database. A slot
must still have its own config, as its tests require (scripts/slot.py).

Usage: python push_guard.py   (pre-commit exports the pushed commit, PRE_COMMIT_TO_REF)
"""

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from git_env import git_environment
from slot import CONFIG, MAIN_PROJECT, checkout_problems, slot_of

ROOT = Path(__file__).resolve().parent.parent
HINT = "Push from that branch's worktree, with a clean tree."


def _project(config: str) -> object:
    try:
        return tomllib.loads(config).get("project_id")
    except tomllib.TOMLDecodeError:
        return None


def push_problems(
    *,
    checkout: Path,
    main_folder: Path,
    head: str,
    pushed: str | None,
    status: str,
    config: str,
) -> list[str]:
    """Why `just check` in `checkout` would not judge the push; empty when it would.

    `pushed` is the commit being pushed, None when no push says it; `status` is
    `git status --porcelain`; `config` is the checkout's supabase/config.toml.
    """
    problems: list[str] = []
    if pushed is not None and pushed != head:
        problems.append(
            f"The push sends {pushed[:12]}, but this checkout is at {head[:12]}: "
            "`just check` would check another tree."
        )
    if status.strip():
        problems.append(
            "The checkout has uncommitted changes or untracked files: `just check` "
            "would check them, not the pushed commits."
        )
    if checkout == main_folder:
        return problems
    slot = slot_of(checkout)
    if slot is not None:
        problems += [
            f"slot {slot}'s {CONFIG} is not its own: {problem}"
            for problem in checkout_problems(checkout, config)
        ]
    elif _project(config) == MAIN_PROJECT:
        problems.append(
            f"This worktree is neither the main folder nor a slot, and its {CONFIG} "
            "is the main folder's: `just check` would reset the main folder's "
            "database. Make it a slot with `just slot N BRANCH`."
        )
    return problems


class _CommandError(Exception):
    pass


def _run(checkout: Path, *args: str) -> str:
    executable = shutil.which(args[0])
    if executable is None:
        raise _CommandError(f"`{args[0]}` is not on PATH: run `just setup`.")
    result = subprocess.run(  # noqa: S603 - a tool on PATH, arguments built here
        [executable, *args[1:]],
        cwd=checkout,
        env=git_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise _CommandError(f"`{' '.join(args)}` failed: {result.stderr.strip()}")
    return result.stdout


def main(*, checkout: Path = ROOT) -> int:
    """`checkout` is the folder the hook runs in: tests pass another."""
    try:
        head = _run(checkout, "git", "rev-parse", "HEAD").strip()
        ref = os.environ.get("PRE_COMMIT_TO_REF")
        pushed = (
            _run(checkout, "git", "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
            if ref
            else None
        )
        status = _run(checkout, "git", "status", "--porcelain")
        common = _run(
            checkout, "git", "rev-parse", "--path-format=absolute", "--git-common-dir"
        )
    except _CommandError as error:
        sys.stderr.write(f"push guard: {error}\n")
        return 1
    config_path = checkout / CONFIG
    config = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    problems = push_problems(
        checkout=checkout.resolve(),
        main_folder=Path(common.strip()).parent.resolve(),
        head=head,
        pushed=pushed,
        status=status,
        config=config,
    )
    if problems:
        for problem in problems:
            sys.stderr.write(f"push guard: {problem}\n")
        sys.stderr.write(f"{HINT}\n")
        return 1
    just = shutil.which("just")
    if just is None:
        sys.stderr.write("push guard: `just` is not on PATH: run `just setup`.\n")
        return 1
    return subprocess.run(  # noqa: S603 - `just check`, resolved on PATH
        [just, "check"], cwd=checkout, env=git_environment(), check=False
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
