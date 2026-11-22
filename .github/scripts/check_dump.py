"""Dump the local database as production's job does, restore it, and compare (TWO-41).

A new Supabase CLI or a new pinned postgres image can add a table whose COPY breaks a
restore, and nothing else would notice before the day a restore is needed. So, against
local Supabase and with only the seed's dev passwords:

1. count and hash the rows of every `app` table and of `auth.users`;
2. run supabase_dump.sh in db_dump.py's pinned image, as `twochi_backup`, through
   Supabase's Docker network, exactly as the daily job runs it;
3. check that data.sql leaves out what ADR 0012 leaves out;
4. rebuild the database from the migrations, without the seed;
5. restore data.sql as `postgres` in one transaction, stopping at the first error;
6. count and hash again, and compare.

Then `supabase db reset` leaves the database as `just reset` does, also after a failure:
the restore brings no role passwords back, and the tests need them. A failed run keeps
its dump files and says where.

Usage:
  python check_dump.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from db_dump import DUMP_IMAGE, DumpError, run_dump_script

ROOT = Path(__file__).resolve().parents[2]
SUPABASE_CONFIG = ROOT / "supabase/config.toml"
# Dev passwords only: the seed's for twochi_backup, the local stack's for postgres.
BACKUP_PASSWORD = "twochi-backup-local"  # noqa: S105
POSTGRES_PASSWORD = "postgres"  # noqa: S105

# What supabase_dump.sh leaves out of data.sql, written out again on purpose: if the
# script lost an exclusion, reading the list from it would lose the check too
# (ADR 0012).
EXCLUDED_TABLES = (
    "auth.schema_migrations",
    "storage.migrations",
    "supabase_functions.migrations",
    "storage.buckets_vectors",
    "storage.vector_indexes",
    "auth.refresh_tokens",
    "auth.sessions",
    "auth.mfa_amr_claims",
    "auth.mfa_challenges",
    "auth.one_time_tokens",
    "auth.flow_state",
)

# `COPY "schema"."table"` while the script keeps --quote-all-identifier, and without
# quotes if it ever drops it: a check that matched nothing would pass in silence.
_COPY = re.compile(r'^COPY "?([^".\s]+)"?\."?([^"\s(]+)"?', re.MULTILINE)


def exclusion_problems(data_sql: str) -> list[str]:
    """Each excluded table whose rows data.sql would restore, as a problem."""
    copied = {f"{schema}.{table}" for schema, table in _COPY.findall(data_sql)}
    if "auth.users" not in copied:
        return [
            "data.sql has no COPY of auth.users, so its exclusions cannot be "
            "checked: did pg_dump's output change?"
        ]
    return [
        f"data.sql copies {table}, which the dump must leave out (ADR 0012)."
        for table in EXCLUDED_TABLES
        if table in copied
    ]


@dataclass(frozen=True, slots=True)
class TableRows:
    count: int
    digest: str  # md5 of the table's rows as text, sorted


def row_differences(
    before: Mapping[str, TableRows], after: Mapping[str, TableRows]
) -> list[str]:
    """Each table whose rows the restore did not bring back as they were."""
    if not any(rows.count for rows in before.values()):
        return [
            "There were no rows to compare: the restore would pass on an empty "
            "database. Is the local seed loaded?"
        ]
    problems: list[str] = []
    for table, rows in before.items():
        restored = after.get(table)
        if restored is None:
            problems.append(
                f"{table} had {rows.count} rows before the dump and is gone after "
                "the restore."
            )
        elif restored.count != rows.count:
            problems.append(
                f"{table} had {rows.count} rows before the dump and "
                f"{restored.count} after the restore."
            )
        elif restored.digest != rows.digest:
            problems.append(
                f"{table} has its {rows.count} rows back, but not as they were dumped."
            )
    return problems


class CheckError(Exception):
    """A step of the check could not run."""


# One query per table through \gexec, each printing `name|count|md5`. Rows hash as text
# in a fixed order, so the same rows give the same digest before and after.
_SNAPSHOT_SQL = r"""
select format(
  'select %L, count(*), '
  'md5(coalesce(string_agg(t::text, E''\n'' order by t::text), '''')) from %s t',
  name, name)
from (
  select format('%I.%I', schemaname, tablename) as name
  from pg_tables
  where schemaname = 'app'
  union all
  select 'auth.users'
) as tables
order by name
\gexec
"""


@dataclass(frozen=True, slots=True)
class LocalDatabase:
    """Local Supabase's Postgres, as containers on its Docker network see it."""

    network: str
    host: str

    @classmethod
    def from_config(cls, config: Path) -> LocalDatabase:
        project = tomllib.loads(config.read_text("utf-8"))["project_id"]
        return cls(network=f"supabase_network_{project}", host=f"supabase_db_{project}")

    def pg(self, user: str, password: str) -> dict[str, str]:
        return {
            "PGHOST": self.host,
            "PGPORT": "5432",  # inside the network, not the host's 553xx
            "PGDATABASE": "postgres",
            "PGUSER": user,
            "PGPASSWORD": password,
            "PGSSLMODE": "disable",  # the local stack has no TLS
        }


def _psql(
    db: LocalDatabase,
    psql_args: Sequence[str],
    *,
    docker_options: Sequence[str] = (),
    stdin: str | None = None,
) -> str:
    """psql from the pinned image, as postgres; its output, or CheckError."""
    pg = db.pg("postgres", POSTGRES_PASSWORD)
    args = ["docker", "run", "--rm", "--network", db.network]
    if stdin is not None:
        args.append("--interactive")
    for name in pg:
        args += ["-e", name]
    args += [*docker_options, DUMP_IMAGE, "psql", "--no-psqlrc", *psql_args]
    result = subprocess.run(  # noqa: S603
        args,
        input=stdin,
        env=os.environ | pg,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise CheckError(f"psql failed with exit code {result.returncode}: see above.")
    return result.stdout


def snapshot(db: LocalDatabase) -> dict[str, TableRows]:
    """Rows of every `app` table and of `auth.users`, by table."""
    output = _psql(
        db,
        ["--tuples-only", "--no-align", "--field-separator=|", "--set=ON_ERROR_STOP=1"],
        stdin=_SNAPSHOT_SQL,
    )
    rows: dict[str, TableRows] = {}
    for line in output.splitlines():
        if line.strip():
            name, count, digest = line.split("|")
            rows[name] = TableRows(count=int(count), digest=digest)
    return rows


def restore(db: LocalDatabase, dump: Path) -> None:
    """data.sql as postgres: one transaction, stopped by its first error."""
    _psql(
        db,
        ["--quiet", "--single-transaction", "--set=ON_ERROR_STOP=1",
         "--file=/dump/data.sql"],
        docker_options=["-v", f"{dump}:/dump:ro"],
    )  # fmt: skip


def _supabase(*args: str) -> None:
    executable = shutil.which("supabase")
    if executable is None:
        raise CheckError("The supabase CLI is not on PATH: run `just setup`.")
    result = subprocess.run([executable, *args], cwd=ROOT, check=False)  # noqa: S603
    if result.returncode != 0:
        raise CheckError(f"`supabase {' '.join(args)}` failed: see above.")


def _check(db: LocalDatabase, work: Path) -> list[str]:
    before = snapshot(db)
    run_dump_script(
        db.pg("twochi_backup", BACKUP_PASSWORD), work, ["--network", db.network]
    )
    if problems := exclusion_problems((work / "data.sql").read_text("utf-8")):
        return problems
    _supabase("db", "reset", "--no-seed")
    restore(db, work)
    return row_differences(before, snapshot(db))


def _error(problem: str) -> None:
    sys.stdout.write(f"::error title=check-dump::{problem}\n")


def _rebuild_with_seed() -> bool:
    """`supabase db reset`, reporting its own failure: it may run while one unwinds."""
    try:
        _supabase("db", "reset")
    except CheckError as error:
        _error(f"The local database could not be rebuilt with its seed: {error}")
        return False
    return True


def main() -> int:
    db = LocalDatabase.from_config(SUPABASE_CONFIG)
    runner_temp = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
    work = Path(tempfile.mkdtemp(prefix="check-dump-", dir=runner_temp)).resolve()
    problems: list[str] = []
    try:
        problems = _check(db, work)
    except (DumpError, CheckError) as error:
        problems = [str(error)]
    finally:
        # Whatever stopped the check, an unexpected error or Ctrl-C included: without
        # the seed's role passwords, every database test fails.
        rebuilt = _rebuild_with_seed()
    for problem in problems:
        _error(problem)
    if problems or not rebuilt:
        sys.stdout.write(f"The dump files stay in {work} for a look.\n")
        return 1
    shutil.rmtree(work, ignore_errors=True)
    sys.stdout.write(
        "Dump restored: data.sql leaves out what ADR 0012 says, and every app table "
        "and auth.users came back as they were.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
