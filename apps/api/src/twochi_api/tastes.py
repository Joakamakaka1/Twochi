"""Tastes at the HTTP edge: the caller's own, and nobody else's (ADR 0015)."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator

from twochi_application.actors import UserActor
from twochi_application.tastes import MyTastes, RatedTaste, RateTaste
from twochi_domain.catalog import ActivityKey, Affinity, FoodKey


class TastesOut(BaseModel):
    """What the caller rated for the pet that represents them; `pet_id` is null and
    `tastes` empty until the pet is born. What was never rated is neutral."""

    pet_id: UUID | None
    tastes: dict[FoodKey | ActivityKey, Affinity]


def _whole_number(value: object) -> object:
    # Pydantic would take "2", 1.0 or true as a rating; only a JSON integer is one.
    if type(value) is not int:
        raise ValueError("affinity is an integer")
    return value


class TasteIn(BaseModel):
    """The caller's affinity with one item, from -2 (hates) to 2 (loves)."""

    affinity: Annotated[Affinity, BeforeValidator(_whole_number)]


class TasteOut(BaseModel):
    """The taste as stored."""

    item_key: FoodKey | ActivityKey
    affinity: Affinity


def tastes_out(tastes: MyTastes) -> TastesOut:
    """Map the use case's result to the response."""
    return TastesOut(pet_id=tastes.pet_id, tastes=dict(tastes.tastes))


def rate_command(
    actor: UserActor, item: FoodKey | ActivityKey, body: TasteIn
) -> RateTaste:
    """Map the request to the use case's command."""
    return RateTaste(actor=actor, item=item, affinity=body.affinity)


def taste_out(rated: RatedTaste) -> TasteOut:
    """Map the stored taste to the response."""
    return TasteOut(item_key=rated.item, affinity=rated.affinity)
