"""Ports: what the use cases need across a network, money or chance boundary."""

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol

from twochi_application.actors import UserActor
from twochi_domain.errors import TwochiError
from twochi_domain.ids import UserId
from twochi_domain.pet import Pet


class Clock(Protocol):
    """Gives the time. Only its adapter reads the system clock."""

    def now(self) -> datetime:
        """The current moment, in UTC."""
        ...


class PetRepository(Protocol):
    """Pets as the actor of the transaction may see them."""

    async def cared_by(self, user_id: UserId) -> Pet | None:
        """The pet this person cares for, or None if it does not exist or is hidden."""
        ...


class Transaction(Protocol):
    """The repositories bound to one open transaction."""

    @property
    def pets(self) -> PetRepository: ...


class Database(Protocol):
    """A minimal unit of work: one transaction per call, with RLS for the actor."""

    def transaction(self, actor: UserActor) -> AbstractAsyncContextManager[Transaction]:
        """Open a transaction that applies RLS with the actor's role and claims."""
        ...


class DatabaseUnavailableError(TwochiError):
    """The database cannot be reached or is not configured."""
