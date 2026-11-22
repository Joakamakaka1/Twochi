"""The typed edge of asyncpg: the few calls the repositories use.

asyncpg ships without complete type hints, so strict pyright cannot see through it. This
module is the only place that touches asyncpg's API; the rest of `twochi_data` sees
these protocols instead.
"""

from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID

import asyncpg  # pyright: ignore[reportMissingTypeStubs]

from twochi_domain.errors import TwochiError


class Row(Protocol):
    """One result row, read by column name."""

    def __getitem__(self, key: str, /) -> object: ...


class Transaction(Protocol):
    """A transaction begun and ended by hand."""

    async def start(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class Connection(Protocol):
    """An open connection; queries take `$1` parameters, never formatted strings."""

    async def execute(self, query: str, /, *args: object) -> str: ...

    async def fetch(self, query: str, /, *args: object) -> list[Row]: ...

    def transaction(self) -> AbstractAsyncContextManager[object]: ...

    def begin(self) -> Transaction: ...

    def is_closed(self) -> bool: ...

    async def close(self) -> None: ...


# Well under the Lambda's 30 s, so a hung connect or query fails as unavailable in
# time instead of holding the container's only connection until the Lambda dies.
CONNECT_TIMEOUT_SECONDS = 5
COMMAND_TIMEOUT_SECONDS = 10


class _AsyncpgConnection:
    """asyncpg's connection under the `Connection` protocol.

    asyncpg is the untyped edge, so the raw connection is `Any` here and nowhere else;
    the `Any` ban covers domain and application, not this adapter's own boundary.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    async def execute(self, query: str, /, *args: object) -> str:
        return cast(str, await self._connection.execute(query, *args))

    async def fetch(self, query: str, /, *args: object) -> list[Row]:
        return cast(list[Row], await self._connection.fetch(query, *args))

    def transaction(self) -> AbstractAsyncContextManager[object]:
        return cast(AbstractAsyncContextManager[object], self._connection.transaction())

    def begin(self) -> Transaction:
        return cast(Transaction, self._connection.transaction())

    def is_closed(self) -> bool:
        return cast(bool, self._connection.is_closed())

    async def close(self) -> None:
        await self._connection.close()


async def connect(dsn: str, *, require_tls: bool = False) -> Connection:
    """Open a connection for the transaction pooler: no prepared statements.

    With `require_tls`, the connection is encrypted or refused, whatever the DSN says;
    asyncpg's default (`prefer`) would fall back to plain text.
    """
    open_connection: Any = asyncpg.connect  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    connection = await open_connection(
        dsn,
        statement_cache_size=0,
        timeout=CONNECT_TIMEOUT_SECONDS,
        command_timeout=COMMAND_TIMEOUT_SECONDS,
        ssl="require" if require_tls else None,
    )
    return _AsyncpgConnection(connection)


def uuid_at(row: Row, key: str) -> UUID:
    """A `uuid` column."""
    return _typed(row, key, UUID)


def text_at(row: Row, key: str) -> str:
    """A `text` column."""
    return _typed(row, key, str)


def int_at(row: Row, key: str) -> int:
    """An integer column, such as a `count(*)`."""
    return _typed(row, key, int)


def float_at(row: Row, key: str) -> float:
    """A `double precision` column."""
    return _typed(row, key, float)


def bool_at(row: Row, key: str) -> bool:
    """A `boolean` column."""
    return _typed(row, key, bool)


def moment_at(row: Row, key: str) -> datetime:
    """A `timestamptz` column, as an aware UTC datetime."""
    return _typed(row, key, datetime).astimezone(UTC)


def optional_moment_at(row: Row, key: str) -> datetime | None:
    """A nullable `timestamptz` column."""
    return None if row[key] is None else moment_at(row, key)


class UnexpectedColumnTypeError(TwochiError):
    """A column came back with a type the query does not promise: a schema drift."""


def _typed[T](row: Row, key: str, kind: type[T]) -> T:
    value = row[key]
    if not isinstance(value, kind):
        raise UnexpectedColumnTypeError(key, type(value).__name__)
    return value


# Errors that mean the database could not be reached or refused the connection.
CONNECT_ERRORS: tuple[type[Exception], ...] = (
    OSError,
    TimeoutError,
    asyncpg.PostgresError,
)

# Errors that mean an open connection was lost: the pooler restarted, the server ended
# the session or the network dropped. Never a bug in a query.
_CONNECTION_LOST_ERRORS: tuple[type[Exception], ...] = (
    OSError,
    TimeoutError,
    asyncpg.ConnectionDoesNotExistError,
    asyncpg.PostgresConnectionError,
    asyncpg.CannotConnectNowError,
    asyncpg.AdminShutdownError,
)


def connection_lost(connection: Connection, error: BaseException) -> bool:
    """Whether `error` means `connection` is gone, rather than a failing query.

    asyncpg reports a lost session as different errors depending on when it notices,
    so a closed connection counts too, whatever the error.
    """
    return connection.is_closed() or isinstance(error, _CONNECTION_LOST_ERRORS)
