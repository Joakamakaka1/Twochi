"""Item affinities: each pet's tastes, as its person rated them."""

from collections.abc import Mapping
from datetime import datetime

from twochi_data.sql import Connection, int_at, text_at
from twochi_domain.catalog import Affinity, ItemKey, item_key
from twochi_domain.ids import PetId

_AFFINITY = """
select affinity::integer as value
from app.item_affinities
where pet_id = $1 and item_key = $2
"""

_TASTES = """
select item_key, affinity::integer as value
from app.item_affinities
where pet_id = $1
"""

# The couple comes from the pet, so the caller never names it. RLS lets the row in only
# when the pet represents the caller (represented_insert and represented_update); a pet
# hidden from them inserts nothing.
_RATE = """
insert into app.item_affinities (couple_id, pet_id, item_key, affinity, updated_at)
select p.couple_id, p.id, $2, $3, $4
from app.pets p
where p.id = $1
on conflict (pet_id, item_key) do update
set affinity = excluded.affinity, updated_at = excluded.updated_at
"""


class PostgresAffinityRepository:
    """Tastes of the pets the transaction's actor may see under RLS.

    Both people of a couple read them; the API decides who is shown what (ADR 0015).
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    async def affinity(self, pet_id: PetId, item: ItemKey) -> Affinity:
        """The pet's affinity with the item; neutral if its person never rated it."""
        rows = await self._connection.fetch(_AFFINITY, pet_id, item.value)
        return Affinity(int_at(rows[0], "value")) if rows else Affinity.NEUTRAL

    async def tastes(self, pet_id: PetId) -> Mapping[ItemKey, Affinity]:
        """What the pet's person rated, skipping keys the catalogue no longer holds."""
        rows = await self._connection.fetch(_TASTES, pet_id)
        tastes: dict[ItemKey, Affinity] = {}
        for row in rows:
            item = item_key(text_at(row, "item_key"))
            if item is not None:
                tastes[item] = Affinity(int_at(row, "value"))
        return tastes

    async def rate(
        self, pet_id: PetId, item: ItemKey, affinity: Affinity, *, at: datetime
    ) -> None:
        """Set the pet's affinity with the item, replacing the one it had."""
        await self._connection.execute(_RATE, pet_id, item.value, int(affinity), at)
