"""`just slot`: a work slot per parallel ticket, with its own local Supabase (TWO-43).

A slot is the git worktree `.claude/worktrees/slot-N` of the main folder. Its
`supabase/config.toml` is rewritten to another project (`twochi-sN`) on ports a hundred
further per slot, so its tests, `supabase db reset` and `check-dump` never reach the
main folder's instance (`twochi`, ports 553xx), which is slot 0 and nobody's to stop.
"""

import re

MAIN_PROJECT = "twochi"
# Twochi's block of local ports; slot N uses the block 100·N further.
MAIN_PORTS = range(55300, 55400)

_PROJECT_LINE = re.compile(r'^project_id\s*=\s*"twochi"', re.MULTILINE)
_FIVE_DIGITS = re.compile(r"(?<!\d)\d{5}(?!\d)")


class SlotError(Exception):
    """The slot cannot be created, removed or committed as asked."""


def project_of(slot: int) -> str:
    return f"{MAIN_PROJECT}-s{slot}"


def slot_config(config: str, slot: int) -> str:
    """The main folder's `supabase/config.toml` as slot `slot` runs it.

    Every 553xx number outside a comment is one of Twochi's ports, also inside a URL.
    """

    def move(number: re.Match[str]) -> str:
        port = int(number[0])
        return str(port + 100 * slot) if port in MAIN_PORTS else number[0]

    lines = (
        line if line.lstrip().startswith("#") else _FIVE_DIGITS.sub(move, line)
        for line in config.splitlines(keepends=True)
    )
    moved, found = _PROJECT_LINE.subn(
        f'project_id = "{project_of(slot)}"', "".join(lines)
    )
    if found != 1:
        raise SlotError(f'The config has no single `project_id = "{MAIN_PROJECT}"`.')
    return moved
