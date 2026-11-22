"""Pre-commit guard: no committed file carries the linked Supabase project's IDs.

`supabase link` writes the production project's ref and organization ID to
`supabase/.temp/linked-project.json`, which git ignores. Tests and docs use fake ones.
In CI or a fresh clone there is no such file and nothing to compare, so the guard
passes. It never prints the IDs.

Usage: python project_ref_guard.py FILE...
"""

import json
import sys
from pathlib import Path

LINKED = Path("supabase/.temp/linked-project.json")
# Opaque IDs only: the project's name and slug are ordinary words.
PRIVATE_KEYS = ("ref", "organization_id")


def main(argv: list[str], linked: Path = LINKED) -> int:
    try:
        project = json.loads(linked.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0
    ids = [
        value.encode()
        for key in PRIVATE_KEYS
        if isinstance(value := project.get(key), str) and value
    ]
    leaks = [
        name
        for name in argv[1:]
        if any(value in Path(name).read_bytes() for value in ids)
    ]
    for name in leaks:
        sys.stderr.write(
            f"{name}: holds the linked Supabase project's ref or organization ID; "
            "use a fake 20-letter one such as abcdefghijklmnopqrst.\n"
        )
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
