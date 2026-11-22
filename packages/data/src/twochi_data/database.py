"""The `Database` port on Postgres with asyncpg, through Supabase's transaction pooler.

Every transaction runs as `authenticated` with the caller's JWT claims (option B of
Datos y vectores): the same RLS policies guard the browser and the API, and a query that
forgets its filter still cannot cross couples. Nothing here runs outside a transaction.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from twochi_application.actors import UserActor
from twochi_application.ports import DatabaseUnavailableError
from twochi_data.pets import PostgresPets
from twochi_data.sql import CONNECT_ERRORS, Connection, connect


class PostgresTransaction:
    """The repositories bound to one open connection and transaction."""

    def __init__(self, connection: Connection) -> None:
        self._pets = PostgresPets(connection)

    @property
    def pets(self) -> PostgresPets:
        return self._pets


class PostgresDatabase:
    """One connection per Lambda container, opened on first use and reopened if lost.

    Without a `dsn` every transaction fails as unavailable, never trying libpq's
    defaults: the API still starts and answers the routes that need no game data.
    """

    def __init__(self, dsn: str | None) -> None:
        self._dsn = dsn
        self._connection: Connection | None = None
        # Requests queue for the single connection instead of interleaving on it.
        self._lock = asyncio.Lock()

    async def _connected(self) -> Connection:
        if self._dsn is None:
            raise DatabaseUnavailableError
        if self._connection is None or self._connection.is_closed():
            try:
                self._connection = await connect(self._dsn)
            except CONNECT_ERRORS as error:
                raise DatabaseUnavailableError from error
        return self._connection

    @asynccontextmanager
    async def transaction(
        self, actor: UserActor
    ) -> AsyncGenerator[PostgresTransaction]:
        """Open a transaction that applies RLS with the actor's role and claims."""
        async with self._lock:
            connection = await self._connected()
            async with connection.transaction():
                # Both are `local`: they end with the transaction, as the pooler needs.
                await connection.execute("set local role authenticated")
                await connection.execute(
                    "select set_config('request.jwt.claims', $1, true)",
                    json.dumps(dict(actor.claims)),
                )
                yield PostgresTransaction(connection)

    async def close(self) -> None:
        """Close the connection, if one is open."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
