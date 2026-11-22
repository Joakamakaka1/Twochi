"""The `Database` adapter when the connection fails: unavailable, then it recovers."""

import pytest
from conftest import ADMIN_URL, API_URL, Couples

from twochi_application.ports import DatabaseUnavailableError
from twochi_data.database import PostgresDatabase
from twochi_data.sql import connect

pytestmark = pytest.mark.anyio


async def drop_api_connections() -> None:
    """Kill every open session of twochi_api, as a pooler restart would."""
    admin = await connect(ADMIN_URL)
    try:
        await admin.execute(
            "select pg_terminate_backend(pid) from pg_stat_activity "
            "where usename = 'twochi_api'"
        )
    finally:
        await admin.close()


async def test_a_connection_lost_mid_transaction_is_unavailable(
    couples: Couples,
) -> None:
    couple = await couples.create()
    actor = couple.actor(couple.bruno)
    db = PostgresDatabase(API_URL, require_tls=False)

    async def read_after_losing_the_connection() -> None:
        async with db.transaction(actor) as tx:
            await drop_api_connections()
            await tx.pets.cared_by(couple.bruno)

    try:
        with pytest.raises(DatabaseUnavailableError):
            await read_after_losing_the_connection()

        # The dead connection is forgotten: the next transaction opens a new one.
        async with db.transaction(actor) as tx:
            assert await tx.pets.cared_by(couple.bruno) is not None
    finally:
        await db.close()


async def test_a_connection_lost_between_transactions_reconnects(
    couples: Couples,
) -> None:
    couple = await couples.create()
    actor = couple.actor(couple.bruno)
    db = PostgresDatabase(API_URL, require_tls=False)
    try:
        async with db.transaction(actor) as tx:
            assert await tx.pets.cared_by(couple.bruno) is not None

        await drop_api_connections()

        async with db.transaction(actor) as tx:
            assert await tx.pets.cared_by(couple.bruno) is not None
    finally:
        await db.close()


async def test_without_a_dsn_every_transaction_is_unavailable(
    couples: Couples,
) -> None:
    couple = await couples.create()
    db = PostgresDatabase(None)

    with pytest.raises(DatabaseUnavailableError):
        async with db.transaction(couple.actor(couple.bruno)):
            pass


async def test_tls_is_required_by_default(couples: Couples) -> None:
    # Local Postgres serves no TLS (`ssl = off`), so a TLS-only connection is refused:
    # the default never falls back to plain text, whatever the DSN says.
    couple = await couples.create()
    db = PostgresDatabase(API_URL)

    with pytest.raises(DatabaseUnavailableError):
        async with db.transaction(couple.actor(couple.bruno)):
            pass
