"""Casa: the pet a person cares for, as it is now."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from twochi_application.actors import UserActor
from twochi_application.ports import Clock, Database
from twochi_domain.catalog import Affinity, ItemKey
from twochi_domain.pet import PetReading, read_pet


@dataclass(frozen=True, slots=True)
class Home:
    """What Casa shows: the pet the person cares for, or None until it is born.

    `discovered` holds the tastes the caretaker discovered: for each item they gave, the
    affinity seen the last time. It comes from the pet's events, never from its tastes,
    so a taste changed since shows only once that item is given again (ADR 0015).
    """

    pet: PetReading | None
    discovered: Mapping[ItemKey, Affinity] = field(
        default_factory=dict[ItemKey, Affinity]
    )


async def get_home(actor: UserActor, *, db: Database, clock: Clock) -> Home:
    """Read the pet the actor cares for at the current moment."""
    async with db.transaction(actor) as tx:
        pet = await tx.pets.cared_by(actor.user_id)
        if pet is None:
            return Home(pet=None)
        discovered = await tx.events.last_reactions(pet.id)
    return Home(pet=read_pet(pet, now=clock.now()), discovered=discovered)
