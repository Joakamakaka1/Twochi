"""The typed edge of asyncpg: the few calls the repositories use.

asyncpg ships without complete type hints, so strict pyright cannot see through it. This
module is the only place that touches asyncpg's API; the rest of `twochi_data` sees
these protocols instead.
"""

from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

import asyncpg  # pyright: ignore[reportMissingTypeStubs]

from twochi_domain.errors import TwochiError


class Row(Protocol):
    """One result row, read by column name."""

    def __getitem__(self, key: str, /) -> object: ...


class Connection(Protocol):
    """An open connection; queries take `$1` parameters, never formatted strings."""

    async def execute(self, query: str, /, *args: object) -> str: ...

    async def fetch(self, query: str, /, *args: object) -> list[Row]: ...

    def transaction(self) -> AbstractAsyncContextManager[object]: ...

    def is_closed(self) -> bool: ...

    async def close(self) -> None: ...


async def connect(dsn: str) -> Connection:
    """Open a connection for the transaction pooler: no prepared statements."""
    return cast(
        Connection,
        await asyncpg.connect(dsn, statement_cache_size=0),  # pyright: ignore[reportUnknownMemberType]
    )


def uuid_at(row: Row, key: str) -> UUID:
    """A `uuid` column."""
    return _typed(row, key, UUID)


def text_at(row: Row, key: str) -> str:
    """A `text` column."""
    return _typed(row, key, str)


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
CONNECT_ERRORS: tuple[type[Exception], ...] = (OSError, asyncpg.PostgresError)
