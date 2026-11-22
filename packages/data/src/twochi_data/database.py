"""The `Database` port on Postgres with asyncpg, through Supabase's transaction pooler.

Every transaction runs as `authenticated` with the caller's JWT claims (option B of
Datos y vectores): the same RLS policies guard the browser and the API, and a query that
forgets its filter still cannot cross couples. Nothing here runs outside a transaction.
"""

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from twochi_application.actors import UserActor
from twochi_application.ports import DatabaseUnavailableError
from twochi_data.pets import PostgresPetRepository
from twochi_data.sql import (
    CONNECT_ERRORS,
    Connection,
    Transaction,
    connect,
    connection_lost,
)


class PostgresTransaction:
    """The repositories bound to one open connection and transaction."""

    def __init__(self, connection: Connection) -> None:
        self._pets = PostgresPetRepository(connection)

    @property
    def pets(self) -> PostgresPetRepository:
        return self._pets


class PostgresDatabase:
    """One connection per Lambda container, opened on first use and reopened if lost.

    Without a `dsn` every transaction fails as unavailable, never trying libpq's
    defaults: the API still starts and answers the routes that need no game data.
    TLS is required unless `require_tls` is turned off, which only local Postgres needs.
    """

    def __init__(self, dsn: str | None, *, require_tls: bool = True) -> None:
        self._dsn = dsn
        self._require_tls = require_tls
        self._connection: Connection | None = None
        # Requests queue for the single connection instead of interleaving on it.
        self._lock = asyncio.Lock()

    async def _connected(self) -> Connection:
        if self._dsn is None:
            raise DatabaseUnavailableError
        if self._connection is None or self._connection.is_closed():
            try:
                self._connection = await connect(
                    self._dsn, require_tls=self._require_tls
                )
            except CONNECT_ERRORS as error:
                raise DatabaseUnavailableError from error
        return self._connection

    @asynccontextmanager
    async def transaction(
        self, actor: UserActor
    ) -> AsyncGenerator[PostgresTransaction]:
        """Open a transaction that applies RLS with the actor's role and claims.

        A connection lost while beginning is replaced once, since nothing ran yet. One
        lost later is unavailable and never retried: what ran is unknown.
        """
        async with self._lock:
            connection, transaction = await self._begin(actor)
            try:
                yield PostgresTransaction(connection)
            except Exception as error:
                await _rollback_quietly(transaction)
                await self._raise_if_lost(connection, error)
                raise
            except BaseException:
                # Cancellation and exits pass through untouched, after the rollback.
                await _rollback_quietly(transaction)
                raise
            try:
                await transaction.commit()
            except Exception as error:
                await self._raise_if_lost(connection, error)
                raise

    async def _begin(self, actor: UserActor) -> tuple[Connection, Transaction]:
        for attempt in range(2):
            connection = await self._connected()
            transaction = connection.begin()
            try:
                await transaction.start()
                # Both are `local`: they end with the transaction, as the pooler needs.
                await connection.execute("set local role authenticated")
                await connection.execute(
                    "select set_config('request.jwt.claims', $1, true)",
                    json.dumps(dict(actor.claims)),
                )
            except Exception as error:
                if not connection_lost(connection, error):
                    await _rollback_quietly(transaction)
                    raise
                await self._forget(connection, error)
                if attempt == 1:
                    raise DatabaseUnavailableError from error
            else:
                return connection, transaction
        raise AssertionError("unreachable")  # pragma: no cover

    async def _raise_if_lost(self, connection: Connection, error: Exception) -> None:
        if connection_lost(connection, error):
            await self._forget(connection, error)
            raise DatabaseUnavailableError from error

    async def _forget(self, connection: Connection, error: Exception) -> None:
        # The next transaction opens a new connection. A timed-out one is still open,
        # so it is closed; a dead one is left to asyncpg, since closing a socket the
        # server already reset only raises again.
        self._connection = None
        if isinstance(error, TimeoutError):
            with contextlib.suppress(Exception):
                await connection.close()

    async def close(self) -> None:
        """Close the connection, if one is open."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None


async def _rollback_quietly(transaction: Transaction) -> None:
    # On a lost connection the rollback fails too; the original error is what matters.
    with contextlib.suppress(Exception):
        await transaction.rollback()
