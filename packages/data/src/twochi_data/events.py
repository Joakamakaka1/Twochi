"""Pet events: the immutable record, written only by inserting."""

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import cast

from twochi_application.ports import CareRecord, StoredCare
from twochi_data.sql import Connection, Row, int_at, text_at, uuid_at
from twochi_domain.care import RULES_VERSION, CareAction, Reaction, SicknessChange
from twochi_domain.catalog import Affinity, ItemKey, item_key
from twochi_domain.errors import TwochiError
from twochi_domain.ids import PetId, UserId
from twochi_domain.needs import Need

_log = logging.getLogger(__name__)

_STORED_CARE = """
select source, action, actor_user_id, deltas::text as deltas,
       payload::text as payload
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

# One pass over the pet's feedings and playings: the last one of each item. Only those
# two actions discover a taste, whatever else an event may name. The pet's lock
# serializes its care actions, so the identity follows the order they were applied in,
# even when the clock went back.
_LAST_REACTIONS = """
select distinct on (payload ->> 'item_key')
  id,
  payload ->> 'item_key' as item_key,
  coalesce((payload -> 'affinity')::text, 'null') as affinity
from app.pet_events
where pet_id = $1
  and action in ('feed', 'play')
  and payload ->> 'item_key' is not null
order by payload ->> 'item_key', id desc
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
    ) -> StoredCare | None:
        """The event already recorded on this pet with this key, if any."""
        rows = await self._connection.fetch(_STORED_CARE, pet_id, idempotency_key)
        return _to_stored_care(rows[0]) if rows else None

    async def effective_pets_since(self, pet_id: PetId, since: datetime) -> int:
        """How many pettings with effect this pet got after `since`."""
        rows = await self._connection.fetch(_EFFECTIVE_PETS_SINCE, pet_id, since)
        return int_at(rows[0], "value")

    async def record_care(
        self, care: CareRecord, *, at: datetime, idempotency_key: str
    ) -> None:
        """Record an applied care action, from the interface, under its key."""
        pet = care.applied.pet
        payload: dict[str, object] = {"effective": care.applied.effective}
        # The item and the affinity seen, for a retry to return the same reaction and
        # for the tastes the caretaker discovers; the sickness change, for the diary.
        if care.applied.reaction is not None:
            payload["item_key"] = care.applied.reaction.item.value
            payload["affinity"] = care.applied.reaction.affinity.value
        if care.applied.sickness is not None:
            payload["sickness"] = care.applied.sickness.value
        await self._connection.execute(
            _RECORD_CARE,
            pet.couple_id,
            pet.id,
            care.actor,
            care.action.value,
            json.dumps(payload),
            json.dumps(
                {need.value: delta for need, delta in care.applied.deltas.items()}
            ),
            RULES_VERSION,
            idempotency_key,
            at,
        )

    async def last_reactions(self, pet_id: PetId) -> Mapping[ItemKey, Affinity]:
        """The affinity seen the last time each item was given to the pet, skipping
        items the catalogue no longer holds."""
        rows = await self._connection.fetch(_LAST_REACTIONS, pet_id)
        seen: dict[ItemKey, Affinity] = {}
        for row in rows:
            item = item_key(text_at(row, "item_key"))
            if item is None:
                continue
            affinity: object = json.loads(text_at(row, "affinity"))
            # A bool passes isinstance as an int: neither it nor 7 is an affinity.
            if type(affinity) is not int or affinity not in Affinity:
                # Casa still opens without that item. Only the id: never the payload.
                _log.warning("care event %s has a broken reaction", int_at(row, "id"))
                continue
            seen[item] = Affinity(affinity)
        return seen


class UnexpectedDeltasError(TwochiError):
    """Stored deltas that are not a map of need to number: a schema drift."""


class UnexpectedPayloadError(TwochiError):
    """A stored payload that is not an object, or names an unknown sickness change."""


def _to_stored_care(row: Row) -> StoredCare:
    action = text_at(row, "action")
    if text_at(row, "source") != "ui" or action not in CareAction:
        # Not a care action from the interface: its deltas need not be a need map.
        return StoredCare(action=None, actor=None, deltas={})
    reaction, sickness = _seen(text_at(row, "payload"))
    return StoredCare(
        action=CareAction(action),
        actor=UserId(uuid_at(row, "actor_user_id")),
        deltas=_to_deltas(text_at(row, "deltas")),
        reaction=reaction,
        sickness=sickness,
    )


def _seen(raw: str) -> tuple[Reaction | None, SicknessChange | None]:
    # The reaction and the sickness change a care event stored. Events from before the
    # tastes carry neither; an item the catalogue no longer holds is ignored, as the
    # tastes ignore it.
    stored: object = json.loads(raw)
    if not isinstance(stored, dict):
        raise UnexpectedPayloadError
    payload = cast(dict[str, object], stored)
    item, affinity = payload.get("item_key"), payload.get("affinity")
    sickness = payload.get("sickness")
    if sickness is not None and sickness not in SicknessChange:
        raise UnexpectedPayloadError
    reaction = None
    known = item_key(item) if isinstance(item, str) else None
    if known is not None:
        # A bool is an int to isinstance; neither it nor a number out of range is one.
        if type(affinity) is not int or affinity not in Affinity:
            raise UnexpectedPayloadError
        reaction = Reaction(item=known, affinity=Affinity(affinity))
    return reaction, None if sickness is None else SicknessChange(sickness)


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
