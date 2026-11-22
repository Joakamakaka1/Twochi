"""Casa: the pet a person cares for, as it is now."""

from dataclasses import dataclass

from twochi_application.actors import UserActor
from twochi_application.ports import Clock, Database
from twochi_domain.pet import PetReading, read_pet


@dataclass(frozen=True, slots=True)
class Home:
    """What Casa shows: the pet the person cares for, or None until it is born."""

    pet: PetReading | None


async def get_home(actor: UserActor, *, db: Database, clock: Clock) -> Home:
    """Read the pet the actor cares for at the current moment."""
    async with db.transaction(actor) as tx:
        pet = await tx.pets.cared_by(actor.user_id)
    if pet is None:
        return Home(pet=None)
    return Home(pet=read_pet(pet, now=clock.now()))
