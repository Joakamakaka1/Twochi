"""`just slot`: a work slot per parallel ticket, with its own local Supabase (TWO-43).

A slot is the git worktree `.claude/worktrees/slot-N` of the main folder. Its
`supabase/config.toml` is rewritten to another project (`twochi-sN`) on ports a hundred
further per slot, so its tests, `supabase db reset` and `check-dump` never reach the
main folder's instance (`twochi`, ports 553xx), which is slot 0 and nobody's to stop.
The rewritten file is hidden from git with skip-worktree, and the pre-commit guard
refuses it if that mark is ever lost. The other way round, a slot whose file went
back to the main folder's is refused by the tests and by `check-dump` before they
reach a database.

Usage:
  python slot.py up N BRANCH       create slot N on BRANCH and start its Supabase
  python slot.py down N [--force]  stop slot N's Supabase and remove its worktree
  python slot.py guard FILE...     pre-commit: a slot's config never enters a commit
  python slot.py check [CHECKOUT]  a slot's checkout still has the slot's config
"""

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import cast

from git_env import git_environment

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


_SLOTS = frozenset(str(slot) for slot in range(1, MAX_SLOT + 1))


def slot_number(raw: str) -> int:
    """`raw` as a slot. Slot 0 is the main folder: nothing here creates or stops it."""
    if raw not in _SLOTS:
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


def slot_of(place: Path) -> int | None:
    """The slot whose worktree `place` is or lies in, by its path; None elsewhere."""
    parts = place.parts
    for at in range(len(parts) - 2):
        hidden, worktrees, name = parts[at : at + 3]
        if (hidden, worktrees) == (".claude", "worktrees"):
            number = name.removeprefix("slot-")
            if name != number and number in _SLOTS:
                return int(number)
    return None


def checkout_problems(checkout: Path, config: str) -> list[str]:
    """Why `config` is not what the slot at `checkout` runs; empty for its own.

    Clearing skip-worktree, a checkout or a merge can bring the main folder's file
    back, and with it the slot's tests and `check-dump` would write to, and reset, the
    main folder's database. A folder that is not a slot is not judged.
    """
    slot = slot_of(checkout)
    if slot is None:
        return []
    try:
        project: object = tomllib.loads(config).get("project_id")
    except tomllib.TOMLDecodeError as error:
        return [f"it is not valid TOML: {error}."]
    own = range(MAIN_PORTS.start + 100 * slot, MAIN_PORTS.stop + 100 * slot)
    problems: list[str] = []
    if project != project_of(slot):
        problems.append(f'project_id is "{project}", not "{project_of(slot)}".')
    problems += [
        f"line {line}: port {port} is not slot {slot}'s, which are "
        f"{own.start // 100}xx."
        for line, port in _ports(config)
        if (port in MAIN_PORTS or port in SLOT_PORTS) and port not in own
    ]
    return problems


def require_own_config(checkout: Path, config: str) -> None:
    """Stop before a database is reached from a slot that lost its config."""
    if problems := checkout_problems(checkout, config):
        slot = slot_of(checkout)
        raise SlotError(
            f"{checkout} is slot {slot}, but its {CONFIG} is not the slot's: "
            f"{problems[0]} Tests and `check-dump` would write to another instance's "
            f"database. `just slot {slot} BRANCH` writes the slot's config again."
        )


def removal_problems(
    *, slot: int, status: str, unpushed: str, config: str, held: str
) -> list[str]:
    """What removing slot `slot`'s worktree would lose.

    From `git status --porcelain` and `git log --oneline HEAD --not --remotes` run in
    it, and from its `supabase/config.toml` (`config`) next to the one git holds at
    HEAD (`held`): skip-worktree hides that file from `git status`, so an edit of it
    shows only as a difference from the slot's rewrite of `held`.
    """
    problems: list[str] = []
    if changes := len(status.splitlines()):
        problems.append(f"{changes} uncommitted changes (`git status`)")
    if commits := len(unpushed.splitlines()):
        problems.append(f"{commits} unpushed commits (`git log HEAD --not --remotes`)")
    try:
        untouched = slot_config(held, slot) == config
    except SlotError:
        untouched = False  # nothing to compare with: it may hold an edit
    if not untouched:
        problems.append(
            f"a {CONFIG} that is not `just slot`'s rewrite, with changes hidden from "
            "`git status` by skip-worktree"
        )
    return problems


# --- The shell around them ------------------------------------------------------------


def _command(args: Sequence[str]) -> list[str]:
    executable = shutil.which(args[0])
    if executable is None:
        raise SlotError(f"`{args[0]}` is not on PATH: run `just setup`.")
    return [executable, *args[1:]]


def _env() -> dict[str, str]:
    # `uv run` exports the venv of the checkout it ran in; a slot's commands use theirs.
    # A hook's GIT_DIR and its kin would point git at another repository than `cwd`.
    return {
        name: value
        for name, value in git_environment().items()
        if name != "VIRTUAL_ENV"
    }


def _succeeds(*args: str, cwd: Path) -> bool:
    result = subprocess.run(_command(args), cwd=cwd, env=_env(), check=False)  # noqa: S603
    return result.returncode == 0


def _run(*args: str, cwd: Path) -> None:
    if not _succeeds(*args, cwd=cwd):
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


def _is_listed(main: Path, folder: Path) -> bool:
    """Whether git still holds `folder` as a worktree of `main`.

    Not `_is_worktree`: in what a failed removal leaves, `git rev-parse` finds the main
    folder above it.
    """
    listing = _output("git", "worktree", "list", "--porcelain", cwd=main)
    return any(
        Path(line.removeprefix("worktree ")).resolve() == folder.resolve()
        for line in listing.splitlines()
        if line.startswith("worktree ")
    )


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
            # --no-track: the new branch is not main's, and must not push there.
            _run(
                "git", "worktree", "add", "--no-track", "-b", branch, str(folder),
                "origin/main", cwd=main,
            )  # fmt: skip
    elif not _is_worktree(folder):
        raise SlotError(
            f"{folder} exists and is not a git worktree: `just slot-down {slot}` "
            "removes it."
        )
    else:
        on = _output("git", "branch", "--show-current", cwd=folder).strip()
        if on != branch:
            raise SlotError(
                f"Slot {slot} is on `{on}`, not `{branch}`: "
                f"`just slot-down {slot}` first."
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


def down(slot: int, *, force: bool, checkout: Path) -> None:
    if slot in {slot_of(checkout), slot_of(Path.cwd())}:
        # Before any side effect: on Windows this very Python and this folder are in
        # use, so Supabase and its data would go and the worktree stay half removed.
        raise SlotError(
            f"Slot {slot} is not removed from inside itself: run "
            f"`just slot-down {slot}` in the main folder."
        )
    main = _main_folder()
    folder = _slot_folder(main, slot)
    # A folder git no longer lists is what a failed removal left: on Windows, git drops
    # the worktree and exits with an error when a process holds one of its files.
    listed = folder.exists() and _is_listed(main, folder)
    if folder.exists() and not listed and (folder / ".git").exists():
        # Leftovers have no `.git`: git deletes it first. This one may hold work.
        raise SlotError(
            f"{folder} is not a worktree of {main} and has its own `.git`: remove it "
            "by hand."
        )
    if listed:
        config = folder / CONFIG
        problems = removal_problems(
            slot=slot,
            status=_output("git", "status", "--porcelain", cwd=folder),
            unpushed=_output(
                "git", "log", "--oneline", "HEAD", "--not", "--remotes", cwd=folder
            ),
            config=config.read_bytes().decode("utf-8") if config.is_file() else "",
            held=_output("git", "show", f"HEAD:{CONFIG}", cwd=folder),
        )
        if problems and not force:
            raise SlotError(
                f"Slot {slot} has {' and '.join(problems)}. Commit and push them, or "
                f"`just slot-down {slot} --force`: the changes are lost and the "
                "commits stay only on the local branch."
            )
    # By name, never by the config found from here: the project is always `twochi-sN`
    # with N from 1, so this cannot stop `twochi`. Its data volumes go too.
    _run("supabase", "stop", "--project-id", project_of(slot), "--no-backup", cwd=main)
    if listed:
        removed = _succeeds(
            "git", "worktree", "remove", *(["--force"] if force else []), str(folder),
            cwd=main,
        )  # fmt: skip
        if not removed and _is_listed(main, folder):
            raise SlotError(f"`git worktree remove` failed for {folder}: see above.")
    # Drops what git still holds of a worktree whose folder is gone.
    _run("git", "worktree", "prune", cwd=main)
    if folder.exists():
        # Git for Windows leaves the folders of node_modules that held pnpm's junctions,
        # and all of a worktree with a file in use. Nothing tracked is left by now.
        try:
            shutil.rmtree(folder)
        except OSError as error:
            raise SlotError(
                f"{folder} is no longer a worktree, but {error}. Close what uses it "
                f"and run `just slot-down {slot}` again."
            ) from error
    sys.stdout.write(f"Slot {slot} is gone: `{project_of(slot)}` stopped.\n")


def check(checkout: Path) -> int:
    try:
        config = (checkout / CONFIG).read_text(encoding="utf-8")
        require_own_config(checkout, config)
    except (OSError, SlotError) as error:
        sys.stderr.write(f"slot: {error}\n")
        return 1
    return 0


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


def main(argv: Sequence[str] | None = None, *, checkout: Path = ROOT) -> int:
    """`checkout` is the folder this script runs from: tests pass another."""
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
    check_command = commands.add_parser("check")
    check_command.add_argument("checkout", nargs="?", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    command = cast(str, args.command)
    if command == "guard":
        return guard(cast(Sequence[Path], args.files))
    if command == "check":
        return check(cast(Path, args.checkout).resolve())
    try:
        # Before anything runs: a wrong number never reaches git or Docker.
        slot = slot_number(cast(str, args.slot))
        if command == "up":
            up(slot, cast(str, args.branch))
        else:
            down(slot, force=cast(bool, args.force), checkout=checkout)
    except SlotError as error:
        sys.stderr.write(f"slot: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
