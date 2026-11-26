"""Item affinities: each pet's tastes, as its person rated them."""

from twochi_data.sql import Connection, int_at
from twochi_domain.catalog import Affinity, ItemKey
from twochi_domain.ids import PetId

_AFFINITY = """
select affinity::integer as value
from app.item_affinities
where pet_id = $1 and item_key = $2
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
