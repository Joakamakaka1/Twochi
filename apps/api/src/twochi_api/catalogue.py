"""The catalogue at the HTTP edge: maps keyed by its items, said so in the contract."""

from typing import Annotated

from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core.core_schema import CoreSchema

from twochi_domain.catalog import CATALOG, ActivityKey, Affinity, FoodKey


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
            "properties": {item.value: value for item in CATALOG},
            "additionalProperties": False,
        }


# An affinity per item of the catalogue: a person's tastes, or what a caretaker saw.
AffinityByItem = Annotated[dict[FoodKey | ActivityKey, Affinity], _CatalogueKeys]
