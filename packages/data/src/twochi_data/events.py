"""Pet events: the immutable record, written only by inserting."""

import json
from collections.abc import Mapping
from datetime import datetime

from twochi_application.ports import CareRecord
from twochi_data.sql import Connection, int_at, text_at
from twochi_domain.care import RULES_VERSION
from twochi_domain.errors import TwochiError
from twochi_domain.ids import PetId
from twochi_domain.needs import Need

_STORED_CARE = """
select deltas::text as deltas
from app.pet_events
where pet_id = $1 and idempotency_key = $2
"""

# `effective` is false only for a petting past the hourly limit.
_EFFECTIVE_PETS_SINCE = """
select count(*) as value
from app.pet_events
where pet_id = $1
  and action = 'pet'
  and created_at > $2
  and (payload ->> 'effective')::boolean
"""

_RECORD_CARE = """
insert into app.pet_events (
  couple_id, pet_id, actor_user_id, source, action, payload, deltas, rules_version,
  idempotency_key, created_at
)
values ($1, $2, $3, 'ui', $4, $5::jsonb, $6::jsonb, $7, $8, $9)
"""


class PostgresPetEventRepository:
    """Events of the pets the transaction's actor may see under RLS."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    async def stored_care(
        self, pet_id: PetId, idempotency_key: str
    ) -> Mapping[Need, float] | None:
        """The deltas of the care action already recorded with this key, if any."""
        rows = await self._connection.fetch(_STORED_CARE, pet_id, idempotency_key)
        return _to_deltas(text_at(rows[0], "deltas")) if rows else None

    async def effective_pets_since(self, pet_id: PetId, since: datetime) -> int:
        """How many pettings with effect this pet got after `since`."""
        rows = await self._connection.fetch(_EFFECTIVE_PETS_SINCE, pet_id, since)
        return int_at(rows[0], "value")

    async def record_care(
        self, care: CareRecord, *, at: datetime, idempotency_key: str
    ) -> None:
        """Record an applied care action, from the interface, under its key."""
        pet = care.applied.pet
        await self._connection.execute(
            _RECORD_CARE,
            pet.couple_id,
            pet.id,
            care.actor,
            care.action.value,
            json.dumps({"effective": care.applied.effective}),
            json.dumps(
                {need.value: delta for need, delta in care.applied.deltas.items()}
            ),
            RULES_VERSION,
            idempotency_key,
            at,
        )


class UnexpectedDeltasError(TwochiError):
    """Stored deltas that are not a map of need to number: a schema drift."""


def _to_deltas(raw: str) -> Mapping[Need, float]:
    stored: object = json.loads(raw)
    if not isinstance(stored, dict):
        raise UnexpectedDeltasError
    deltas: dict[Need, float] = {}
    for need, delta in stored.items():  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(delta, int | float) or need not in Need:
            raise UnexpectedDeltasError
        deltas[Need(need)] = float(delta)
    return deltas
