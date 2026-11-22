"""The daily dump's login role reads every row and writes to no table (ADR 0012)."""

from collections.abc import AsyncIterator

import pytest
from conftest import BACKUP_URL, Couples

from twochi_data.sql import Connection, connect

pytestmark = pytest.mark.anyio


@pytest.fixture
async def backup() -> AsyncIterator[Connection]:
    connection = await connect(BACKUP_URL)
    try:
        yield connection
    finally:
        await connection.close()


async def test_reads_every_couple_past_rls(
    couples: Couples, backup: Connection
) -> None:
    ours = await couples.create()
    theirs = await couples.create()

    rows = await backup.fetch(
        "select couple_id from app.pets where couple_id = any($1::uuid[])",
        [ours.id, theirs.id],
    )

    assert sorted(str(row["couple_id"]) for row in rows) == sorted(
        map(str, [ours.id, ours.id, theirs.id, theirs.id])
    )


@pytest.mark.parametrize(
    "statement",
    [
        "insert into app.couples (timezone) values ('Europe/Madrid')",
        "update auth.users set email = email",
        "delete from app.signup_allowlist",
        "create table public.dump_probe (id int)",
        "create schema dump_probe",
        "alter role twochi_backup nobypassrls",
    ],
)
async def test_writes_nothing_even_when_it_lifts_read_only(
    backup: Connection, statement: str
) -> None:
    await backup.execute("set default_transaction_read_only = off")

    with pytest.raises(Exception, match="permission denied"):
        await backup.execute(statement)


async def test_runs_no_function_with_its_owners_rights(backup: Connection) -> None:
    # pg_read_all_data opens every schema, so a SECURITY DEFINER function that PUBLIC
    # may execute, in any schema, would let the role write as that function's owner.
    rows = await backup.fetch(
        "select p.oid::regprocedure::text as name from pg_proc p "
        "where p.prosecdef and has_function_privilege(p.oid, 'execute')"
    )

    assert [row["name"] for row in rows] == []
