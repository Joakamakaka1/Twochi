"""`just slot`: a work slot per parallel ticket, with its own local Supabase (TWO-43).

A slot is the git worktree `.claude/worktrees/slot-N` of the main folder. Its
`supabase/config.toml` is rewritten to another project (`twochi-sN`) on ports a hundred
further per slot, so its tests, `supabase db reset` and `check-dump` never reach the
main folder's instance (`twochi`, ports 553xx), which is slot 0 and nobody's to stop.
The rewritten file is hidden from git with skip-worktree, and the pre-commit guard
refuses it if that mark is ever lost.

Usage:
  python slot.py up N BRANCH       create slot N on BRANCH and start its Supabase
  python slot.py down N [--force]  stop slot N's Supabase and remove its worktree
  python slot.py guard FILE...     pre-commit: a slot's config never enters a commit
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent
CONFIG = "supabase/config.toml"

MAIN_PROJECT = "twochi"
MAX_SLOT = 9
# Twochi's block of local ports; slot N uses the block 100·N further.
MAIN_PORTS = range(55300, 55400)
SLOT_PORTS = range(MAIN_PORTS.stop, MAIN_PORTS.stop + 100 * MAX_SLOT)

# What CI's `supabase start` leaves out: Postgres, Auth and its gateway stay. A test
# keeps this in step with ci.yml.
EXCLUDED_SERVICES = (
    "realtime,storage-api,imgproxy,mailpit,postgrest,postgres-meta,studio,"
    "edge-runtime,logflare,vector,supavisor"
)

_PROJECT_LINE = re.compile(r'^project_id\s*=\s*"twochi"', re.MULTILINE)
_FIVE_DIGITS = re.compile(r"(?<!\d)\d{5}(?!\d)")


class SlotError(Exception):
    """The slot cannot be created or removed as asked."""


# --- Decisions, on plain text ---------------------------------------------------------


def slot_number(raw: str) -> int:
    """`raw` as a slot. Slot 0 is the main folder: nothing here creates or stops it."""
    if raw not in {str(slot) for slot in range(1, MAX_SLOT + 1)}:
        raise SlotError(
            f"`{raw}` is no slot: slots go from 1 to {MAX_SLOT}. Slot 0 is the main "
            "folder, which `just up` and `just down` start and stop."
        )
    return int(raw)


def project_of(slot: int) -> str:
    return f"{MAIN_PROJECT}-s{slot}"


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _ports(config: str) -> Iterator[tuple[int, int]]:
    """Each five-digit number outside a comment, with its line: URLs hold ports too."""
    for number, line in enumerate(config.splitlines(), start=1):
        if not _is_comment(line):
            for found in _FIVE_DIGITS.finditer(line):
                yield number, int(found[0])


def config_problems(config: str) -> list[str]:
    """Why `config` is not the main folder's `supabase/config.toml`; empty if it is."""
    try:
        project: object = tomllib.loads(config).get("project_id")
    except tomllib.TOMLDecodeError as error:
        return [f"it is not valid TOML: {error}."]
    problems: list[str] = []
    if project != MAIN_PROJECT:
        problems.append(f'project_id is "{project}", not "{MAIN_PROJECT}".')
    problems += [
        f"line {line}: port {port} is slot {(port - MAIN_PORTS.start) // 100}'s; "
        "the main folder's are 553xx."
        for line, port in _ports(config)
        if port in SLOT_PORTS
    ]
    return problems


def slot_config(config: str, slot: int) -> str:
    """The main folder's `supabase/config.toml` as slot `slot` runs it.

    Every 553xx number outside a comment is one of Twochi's ports, also inside a URL.
    """
    if problems := config_problems(config):
        # Moving a slot's ports again would land on yet another slot's.
        raise SlotError(f"This is not the main folder's config: {problems[0]}")

    def move(number: re.Match[str]) -> str:
        port = int(number[0])
        return str(port + 100 * slot) if port in MAIN_PORTS else number[0]

    lines = (
        line if _is_comment(line) else _FIVE_DIGITS.sub(move, line)
        for line in config.splitlines(keepends=True)
    )
    moved, found = _PROJECT_LINE.subn(
        f'project_id = "{project_of(slot)}"', "".join(lines)
    )
    if found != 1:
        raise SlotError(f'The config has no single `project_id = "{MAIN_PROJECT}"`.')
    return moved


def removal_problems(*, status: str, unpushed: str) -> list[str]:
    """What removing a worktree would lose, from `git status --porcelain` and
    `git log --oneline HEAD --not --remotes` run in it."""
    problems: list[str] = []
    if changes := len(status.splitlines()):
        problems.append(f"{changes} uncommitted changes (`git status`)")
    if commits := len(unpushed.splitlines()):
        problems.append(f"{commits} unpushed commits (`git log HEAD --not --remotes`)")
    return problems


# --- The shell around them ------------------------------------------------------------


def _command(args: Sequence[str]) -> list[str]:
    executable = shutil.which(args[0])
    if executable is None:
        raise SlotError(f"`{args[0]}` is not on PATH: run `just setup`.")
    return [executable, *args[1:]]


def _env() -> dict[str, str]:
    # `uv run` exports the venv of the checkout it ran in; a slot's commands use theirs.
    return {name: value for name, value in os.environ.items() if name != "VIRTUAL_ENV"}


def _run(*args: str, cwd: Path) -> None:
    result = subprocess.run(_command(args), cwd=cwd, env=_env(), check=False)  # noqa: S603
    if result.returncode != 0:
        raise SlotError(f"`{' '.join(args)}` failed in {cwd}: see above.")


def _output(*args: str, cwd: Path) -> str:
    result = subprocess.run(  # noqa: S603
        _command(args),
        cwd=cwd,
        env=_env(),
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise SlotError(f"`{' '.join(args)}` failed in {cwd}: see above.")
    return result.stdout


def _has_ref(ref: str, cwd: Path) -> bool:
    result = subprocess.run(  # noqa: S603
        _command(["git", "show-ref", "--verify", "--quiet", ref]), cwd=cwd, check=False
    )
    return result.returncode == 0


def _main_folder() -> Path:
    """The main checkout, also when this runs from a worktree of it."""
    common = _output(
        "git", "rev-parse", "--path-format=absolute", "--git-common-dir", cwd=ROOT
    )
    return Path(common.strip()).parent


def _slot_folder(main: Path, slot: int) -> Path:
    return main / ".claude" / "worktrees" / f"slot-{slot}"


def _is_worktree(folder: Path) -> bool:
    top = _output("git", "rev-parse", "--show-toplevel", cwd=folder).strip()
    return Path(top).resolve() == folder.resolve()


def up(slot: int, branch: str) -> None:
    if branch.startswith("-"):
        raise SlotError(f"`{branch}` is not a branch name.")
    main = _main_folder()
    folder = _slot_folder(main, slot)
    if not folder.exists():
        _run("git", "fetch", "origin", cwd=main)
        known = _has_ref(f"refs/heads/{branch}", main) or _has_ref(
            f"refs/remotes/origin/{branch}", main
        )
        if known:
            _run("git", "worktree", "add", str(folder), branch, cwd=main)
        else:
            _run(
                "git", "worktree", "add", "-b", branch, str(folder), "origin/main",
                cwd=main,
            )  # fmt: skip
    elif not _is_worktree(folder):
        raise SlotError(f"{folder} exists and is not a git worktree.")
    elif (on := _output("git", "branch", "--show-current", cwd=folder).strip()) != (
        branch
    ):
        raise SlotError(
            f"Slot {slot} is on `{on}`, not `{branch}`: `just slot-down {slot}` first."
        )

    # From what git holds, not from the file: running this again changes nothing.
    config = slot_config(_output("git", "show", f"HEAD:{CONFIG}", cwd=folder), slot)
    (folder / CONFIG).write_bytes(config.encode("utf-8"))
    _run("git", "update-index", "--skip-worktree", CONFIG, cwd=folder)

    _run("uv", "sync", "--locked", cwd=folder)
    _run("pnpm", "install", "--frozen-lockfile", cwd=folder)
    # --workdir: without it the CLI looks for a supabase/ folder upwards, and above a
    # slot is the main folder's.
    _run(
        "supabase", "start", "--workdir", str(folder), "-x", EXCLUDED_SERVICES,
        cwd=folder,
    )  # fmt: skip
    port = tomllib.loads(config)["db"]["port"]
    sys.stdout.write(
        f"Slot {slot} is up: {folder} on `{branch}`, Supabase `{project_of(slot)}` "
        f"with Postgres on {port}.\n"
    )


def down(slot: int, *, force: bool) -> None:
    main = _main_folder()
    folder = _slot_folder(main, slot)
    if folder.exists():
        if not _is_worktree(folder):
            raise SlotError(f"{folder} is not a git worktree: remove it by hand.")
        problems = removal_problems(
            status=_output("git", "status", "--porcelain", cwd=folder),
            unpushed=_output(
                "git", "log", "--oneline", "HEAD", "--not", "--remotes", cwd=folder
            ),
        )
        if problems and not force:
            raise SlotError(
                f"Slot {slot} has {' and '.join(problems)}, which removing it would "
                f"lose. Save them, or `just slot-down {slot} --force`."
            )
    # By name, never by the config found from here: the project is always `twochi-sN`
    # with N from 1, so this cannot stop `twochi`. Its data volumes go too.
    _run("supabase", "stop", "--project-id", project_of(slot), "--no-backup", cwd=main)
    if folder.exists():
        _run(
            "git", "worktree", "remove", *(["--force"] if force else []), str(folder),
            cwd=main,
        )  # fmt: skip
    sys.stdout.write(f"Slot {slot} is gone: `{project_of(slot)}` stopped.\n")


def guard(files: Sequence[Path]) -> int:
    refused = False
    for file in files:
        for problem in config_problems(file.read_text(encoding="utf-8")):
            sys.stderr.write(f"{file}: {problem}\n")
            refused = True
    if refused:
        sys.stderr.write(
            "A slot's Supabase config never enters a commit. Unstage it and hide it "
            "again: `git restore --staged supabase/config.toml && git update-index "
            "--skip-worktree supabase/config.toml`.\n"
        )
    return 1 if refused else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="slot")
    commands = parser.add_subparsers(dest="command", required=True)
    up_command = commands.add_parser("up")
    up_command.add_argument("slot")
    up_command.add_argument("branch")
    down_command = commands.add_parser("down")
    down_command.add_argument("slot")
    down_command.add_argument(
        "--force",
        action="store_true",
        help="Remove the worktree with its uncommitted changes and unpushed commits.",
    )
    guard_command = commands.add_parser("guard")
    guard_command.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args(argv)
    command = cast(str, args.command)
    if command == "guard":
        return guard(cast(Sequence[Path], args.files))
    try:
        # Before anything runs: a wrong number never reaches git or Docker.
        slot = slot_number(cast(str, args.slot))
        if command == "up":
            up(slot, cast(str, args.branch))
        else:
            down(slot, force=cast(bool, args.force))
    except SlotError as error:
        sys.stderr.write(f"slot: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
