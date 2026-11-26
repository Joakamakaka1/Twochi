"""Ports: what the use cases need across a network, money or chance boundary."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from twochi_application.actors import UserActor
from twochi_domain.care import Applied, CareAction, Reaction, SicknessChange
from twochi_domain.catalog import Affinity, ItemKey
from twochi_domain.errors import TwochiError
from twochi_domain.ids import PetId, UserId
from twochi_domain.needs import Need
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

    async def representing(self, user_id: UserId) -> PetId | None:
        """The pet that represents this person, or None if not born yet or hidden."""
        ...

    async def lock(self, pet_id: PetId) -> Pet | None:
        """A pet and its needs, locked until the transaction ends; None if hidden."""
        ...

    async def save(self, pet: Pet) -> None:
        """Store the pet's sleep state, sickness and needs."""
        ...


class AffinityRepository(Protocol):
    """The tastes of the pets the actor may see: each pet's affinity with an item."""

    async def affinity(self, pet_id: PetId, item: ItemKey) -> Affinity:
        """The pet's affinity with the item; neutral if its person never rated it."""
        ...

    async def tastes(self, pet_id: PetId) -> Mapping[ItemKey, Affinity]:
        """What the pet's person rated, skipping keys the catalogue no longer holds."""
        ...

    async def rate(
        self, pet_id: PetId, item: ItemKey, affinity: Affinity, *, at: datetime
    ) -> None:
        """Set the pet's affinity with the item, replacing the one it had."""
        ...


class PetEventRepository(Protocol):
    """The immutable record of what happens to the pets the actor may see."""

    async def stored_care(
        self, pet_id: PetId, idempotency_key: str
    ) -> StoredCare | None:
        """The event already recorded on this pet with this key, if any."""
        ...

    async def effective_pets_since(self, pet_id: PetId, since: datetime) -> int:
        """How many pettings with effect this pet got after `since`."""
        ...

    async def record_care(
        self, care: CareRecord, *, at: datetime, idempotency_key: str
    ) -> None:
        """Record an applied care action, from the interface, under its key."""
        ...

    async def last_reactions(self, pet_id: PetId) -> Mapping[ItemKey, Affinity]:
        """The affinity seen the last time each item was given to the pet, skipping
        items the catalogue no longer holds."""
        ...


@dataclass(frozen=True, slots=True)
class StoredCare:
    """An event found by its key. `action` is None when it is not a care action from
    the interface, such as a birth; its deltas are then left empty. The reaction and
    the sickness change are the ones seen when it was applied."""

    action: CareAction | None
    actor: UserId | None
    deltas: Mapping[Need, float]
    reaction: Reaction | None = None
    sickness: SicknessChange | None = None


@dataclass(frozen=True, slots=True)
class CareRecord:
    """An applied care action as its event stores it: the pet is the one after it."""

    actor: UserId
    action: CareAction
    applied: Applied


class Transaction(Protocol):
    """The repositories bound to one open transaction."""

    @property
    def pets(self) -> PetRepository: ...

    @property
    def events(self) -> PetEventRepository: ...

    @property
    def affinities(self) -> AffinityRepository: ...


class Database(Protocol):
    """A minimal unit of work: one transaction per call, with RLS for the actor."""

    def transaction(self, actor: UserActor) -> AbstractAsyncContextManager[Transaction]:
        """Open a transaction that applies RLS with the actor's role and claims."""
        ...


class DatabaseUnavailableError(TwochiError):
    """The database cannot be reached or is not configured."""
