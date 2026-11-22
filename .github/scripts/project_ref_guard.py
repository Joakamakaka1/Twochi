"""Pre-commit and commit-msg guard: nothing committed carries the linked Supabase IDs.

`supabase link` writes the production project's ref and organization IDs into
`supabase/.temp`, which git ignores: `linked-project.json` in the CLI pinned today,
`project-ref` in others. Tests and docs use fake ones. A worktree has no gitignored
files, so the main checkout's folder counts too. In CI or a fresh clone there is no
such file and nothing to compare, so the guard passes. It never prints the IDs.

Usage: python project_ref_guard.py FILE...
"""

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

TEMP_DIR = Path("supabase/.temp")
# Opaque IDs only: the project's name is an ordinary word. The organization slug is a
# random string too.
PRIVATE_KEYS = ("ref", "organization_id", "organization_slug")


class BrokenLinkError(Exception):
    pass


def default_temp_dirs() -> list[Path]:
    """This checkout's `supabase/.temp`, then the main checkout's for a worktree."""
    dirs = [TEMP_DIR]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # no git on PATH
        return dirs
    if result.returncode != 0:
        return dirs
    main_dir = Path(result.stdout.strip()).parent / TEMP_DIR
    if main_dir.resolve() != TEMP_DIR.resolve():
        dirs.append(main_dir)
    return dirs


def linked_ids(temp_dir: Path) -> list[bytes]:
    """The private IDs `supabase link` left in `temp_dir`; empty when not linked."""
    ids: list[bytes] = []
    ref_file = temp_dir / "project-ref"
    if ref_file.is_file():
        ids.append(ref_file.read_bytes().strip())
    linked = temp_dir / "linked-project.json"
    if linked.is_file():
        try:
            project = json.loads(linked.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise BrokenLinkError(str(linked)) from error
        if not isinstance(project, dict):
            raise BrokenLinkError(str(linked))
        values = (project.get(key) for key in PRIVATE_KEYS)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        found = [value.encode() for value in values if isinstance(value, str) and value]
        # A CLI that renamed its keys must not turn the guard off without a word.
        if not found:
            raise BrokenLinkError(str(linked))
        ids += found
    return [value for value in ids if value]


def main(argv: list[str], temp_dirs: Sequence[Path] | None = None) -> int:
    try:
        ids = [
            value
            for folder in (default_temp_dirs() if temp_dirs is None else temp_dirs)
            for value in linked_ids(folder)
        ]
    except BrokenLinkError as error:
        sys.stderr.write(f"{error} is not valid: run `supabase link` again.\n")
        return 1
    # UTF-16 too: Windows PowerShell 5.1 writes it when output is redirected.
    needles = [
        form for value in ids for form in (value, value.decode().encode("utf-16-le"))
    ]
    leaks = [
        name
        for name in argv[1:]
        if any(needle in Path(name).read_bytes() for needle in needles)
    ]
    for name in leaks:
        sys.stderr.write(
            f"{name}: holds the linked Supabase project's ref or organization ID; "
            "use a fake 20-letter one such as abcdefghijklmnopqrst.\n"
        )
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
