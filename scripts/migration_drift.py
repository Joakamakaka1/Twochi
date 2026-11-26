"""Whether the local database is behind the repo's migrations (TWO-59).

A checkout that brings a migration from `main` without `just reset` leaves its database
behind, and every test that reaches the new table fails on its own. The root conftest
asks this module once, before the first test that uses the database, and stops the
session with one message instead.

Migrations compare by version and name, not by version alone: after a rebase renumbers
a branch's migration, the slot's database still holds it under the number `main` took.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

# What the Supabase CLI applies from supabase/migrations: any other file it skips.
_MIGRATION_FILE = re.compile(r"^(?P<migration>\d+_.*)\.sql$")


@dataclass(frozen=True, slots=True)
class MigrationDrift:
    pending: tuple[str, ...]  # files in the repo the database has not applied
    gone: tuple[str, ...]  # `<version>_<name>` applied, with no file in the repo

    def message(self) -> str:
        lines = ["The local database does not match supabase/migrations."]
        if self.pending:
            lines.append("Not applied: " + ", ".join(self.pending) + ".")
        if self.gone:
            lines.append(
                "Applied but no longer in the repo: " + ", ".join(self.gone) + "."
            )
        lines.append("Rebuild it with `just reset`, then run the tests again.")
        return "\n".join(lines)


def migration_drift(
    files: Iterable[str], applied: Iterable[str]
) -> MigrationDrift | None:
    """How `applied`, as `<version>_<name>`, differs from the migration `files`.

    None when the database holds exactly the repo's migrations.
    """
    migrations = {
        match["migration"]: file
        for file in files
        if (match := _MIGRATION_FILE.match(file))
    }
    done = set(applied)
    pending = tuple(
        sorted(file for name, file in migrations.items() if name not in done)
    )
    gone = tuple(sorted(done - migrations.keys()))
    if not pending and not gone:
        return None
    return MigrationDrift(pending=pending, gone=gone)
