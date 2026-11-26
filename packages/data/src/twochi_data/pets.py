"""Pets and their needs: hand-written SQL that returns domain types."""

from collections.abc import Sequence

from twochi_data.sql import (
    Connection,
    Row,
    bool_at,
    float_at,
    moment_at,
    optional_moment_at,
    text_at,
    uuid_at,
)
from twochi_domain.ids import CoupleId, PetId, UserId
from twochi_domain.needs import Need, NeedState
from twochi_domain.pet import Pet

_CARED_BY = """
select p.id, p.couple_id, p.represents_user_id, p.caretaker_user_id, p.name,
       p.model_key, p.asleep, p.sick_since, n.need, n.value, n.updated_at
from app.pets p
join app.pet_needs n on n.pet_id = p.id
where p.caretaker_user_id = $1
"""

_REPRESENTING = """
select p.id
from app.pets p
where p.represents_user_id = $1
"""

# Locks the pet's row and its five needs: a second action on the same pet waits here
# until the first commits, then reads what the first one wrote.
_LOCK = """
select p.id, p.couple_id, p.represents_user_id, p.caretaker_user_id, p.name,
       p.model_key, p.asleep, p.sick_since, n.need, n.value, n.updated_at
from app.pets p
join app.pet_needs n on n.pet_id = p.id
where p.id = $1
for update
"""

# One round trip: the pet's state and its five needs in one statement.
_SAVE = """
with pet as (
  update app.pets set asleep = $2, sick_since = $3 where id = $1
)
update app.pet_needs n
set value = s.value, updated_at = s.updated_at
from unnest($4::text[], $5::float8[], $6::timestamptz[]) as s (need, value, updated_at)
where n.pet_id = $1 and n.need = s.need
"""


class PostgresPetRepository:
    """Pets as the transaction's actor may see them under RLS."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    async def cared_by(self, user_id: UserId) -> Pet | None:
        """The pet this person cares for, or None if it does not exist or is hidden."""
        rows = await self._connection.fetch(_CARED_BY, user_id)
        return _to_pet(rows) if rows else None

    async def representing(self, user_id: UserId) -> PetId | None:
        """The pet that represents this person, or None if not born yet or hidden."""
        rows = await self._connection.fetch(_REPRESENTING, user_id)
        return PetId(uuid_at(rows[0], "id")) if rows else None

    async def lock(self, pet_id: PetId) -> Pet | None:
        """A pet and its needs, locked until the transaction ends; None if hidden."""
        rows = await self._connection.fetch(_LOCK, pet_id)
        return _to_pet(rows) if rows else None

    async def save(self, pet: Pet) -> None:
        """Store the pet's sleep state, sickness and needs."""
        needs = list(pet.needs.items())
        await self._connection.execute(
            _SAVE,
            pet.id,
            pet.asleep,
            pet.sick_since,
            [need.value for need, _ in needs],
            [state.value for _, state in needs],
            [state.updated_at for _, state in needs],
        )


def _to_pet(rows: Sequence[Row]) -> Pet:
    # One row per need, all of the same pet.
    first = rows[0]
    return Pet(
        id=PetId(uuid_at(first, "id")),
        couple_id=CoupleId(uuid_at(first, "couple_id")),
        represents_user_id=UserId(uuid_at(first, "represents_user_id")),
        caretaker_user_id=UserId(uuid_at(first, "caretaker_user_id")),
        name=text_at(first, "name"),
        model_key=text_at(first, "model_key"),
        needs={
            Need(text_at(row, "need")): NeedState(
                value=float_at(row, "value"), updated_at=moment_at(row, "updated_at")
            )
            for row in rows
        },
        asleep=bool_at(first, "asleep"),
        sick_since=optional_moment_at(first, "sick_since"),
    )
