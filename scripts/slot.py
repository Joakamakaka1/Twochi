"""`just slot`: a work slot per parallel ticket, with its own local Supabase (TWO-43).

A slot is the git worktree `.claude/worktrees/slot-N` of the main folder. Its
`supabase/config.toml` is rewritten to another project (`twochi-sN`) on ports a hundred
further per slot, so its tests, `supabase db reset` and `check-dump` never reach the
main folder's instance (`twochi`, ports 553xx), which is slot 0 and nobody's to stop.

Usage:
  python slot.py guard FILE...   pre-commit: a slot's config never enters a commit
"""

import argparse
import re
import sys
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import cast

MAIN_PROJECT = "twochi"
MAX_SLOT = 9
# Twochi's block of local ports; slot N uses the block 100·N further.
MAIN_PORTS = range(55300, 55400)
SLOT_PORTS = range(MAIN_PORTS.stop, MAIN_PORTS.stop + 100 * MAX_SLOT)

_PROJECT_LINE = re.compile(r'^project_id\s*=\s*"twochi"', re.MULTILINE)
_FIVE_DIGITS = re.compile(r"(?<!\d)\d{5}(?!\d)")


class SlotError(Exception):
    """The slot cannot be created or removed as asked."""


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
    guard_command = commands.add_parser("guard")
    guard_command.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args(argv)
    return guard(cast(Sequence[Path], args.files))


if __name__ == "__main__":
    sys.exit(main())
