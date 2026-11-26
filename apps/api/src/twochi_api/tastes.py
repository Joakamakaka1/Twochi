"""Tastes at the HTTP edge: the caller's own, and nobody else's (ADR 0015)."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core.core_schema import CoreSchema

from twochi_application.actors import UserActor
from twochi_application.tastes import MyTastes, RatedTaste, RateTaste
from twochi_domain.catalog import ActivityKey, Affinity, FoodKey


class _CatalogueKeys:
    """A map keyed by the catalogue, said so in the contract.

    `propertyNames` names the enums, as JSON Schema says it. The generated client does
    not read it, so each item is also an optional property and nothing else is allowed:
    a key outside the catalogue breaks the front's build.
    """

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        mapping = handler(schema)
        keys = schema.get("keys_schema")
        if schema["type"] != "dict" or keys is None:  # pragma: no cover - map only
            return mapping
        # The values' schema as the map's own: a reference to Affinity, not a copy.
        value = mapping["additionalProperties"]
        return {
            "type": "object",
            "propertyNames": handler(keys),
            "properties": {item.value: value for item in (*FoodKey, *ActivityKey)},
            "additionalProperties": False,
        }


class TastesOut(BaseModel):
    """What the caller rated for the pet that represents them; `pet_id` is null and
    `tastes` empty until the pet is born. What was never rated is neutral."""

    pet_id: UUID | None
    tastes: Annotated[dict[FoodKey | ActivityKey, Affinity], _CatalogueKeys]


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
