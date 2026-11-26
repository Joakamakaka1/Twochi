"""Tastes: each person rates the pet that represents them.

No use case here, or anywhere, returns the tastes of the pet the actor cares for: the
caretaker discovers them by caring (ADR 0015). That boundary is the shape of these
functions, which only ever look up the actor's own pet.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from twochi_application.actors import UserActor
from twochi_application.ports import Clock, Database
from twochi_domain.catalog import Affinity, ItemKey
from twochi_domain.errors import TwochiError
from twochi_domain.ids import PetId


@dataclass(frozen=True, slots=True)
class MyTastes:
    """The tastes of the pet that represents the actor: only what they rated.

    `pet_id` is None until the pet is born; the tastes are then empty.
    """

    pet_id: PetId | None
    tastes: Mapping[ItemKey, Affinity]


@dataclass(frozen=True, slots=True)
class RateTaste:
    """A person rates an item of the catalogue for the pet that represents them."""

    actor: UserActor
    item: ItemKey
    affinity: Affinity


@dataclass(frozen=True, slots=True)
class RatedTaste:
    """The taste as stored."""

    pet_id: PetId
    item: ItemKey
    affinity: Affinity


class NoPetYetError(TwochiError):
    """The pet that represents the actor is not born yet, or is hidden from them."""


async def get_my_tastes(actor: UserActor, *, db: Database) -> MyTastes:
    """Read what the actor rated for the pet that represents them."""
    async with db.transaction(actor) as tx:
        pet_id = await tx.pets.representing(actor.user_id)
        if pet_id is None:
            return MyTastes(pet_id=None, tastes={})
        return MyTastes(pet_id=pet_id, tastes=await tx.affinities.tastes(pet_id))


async def rate_taste(cmd: RateTaste, *, db: Database, clock: Clock) -> RatedTaste:
    """Set, or replace, the affinity of the actor's own pet with an item."""
    async with db.transaction(cmd.actor) as tx:
        pet_id = await tx.pets.representing(cmd.actor.user_id)
        if pet_id is None:
            raise NoPetYetError
        await tx.affinities.rate(pet_id, cmd.item, cmd.affinity, at=clock.now())
    return RatedTaste(pet_id=pet_id, item=cmd.item, affinity=cmd.affinity)
