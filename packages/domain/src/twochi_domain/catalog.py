"""The catalogue: the foods and activities a caretaker may choose, and the tastes.

The catalogue is versioned with the rules of the game (`RULES_VERSION`). Names and
icons are interface, so they live in the front, keyed by these stable keys.
"""

from collections.abc import Mapping
from enum import IntEnum, StrEnum
from types import MappingProxyType

from twochi_domain.errors import TwochiError


class ItemKind(StrEnum):
    """What an item of the catalogue is: food goes to hunger, an activity to fun."""

    FOOD = "food"
    ACTIVITY = "activity"


class ItemKey(StrEnum):
    """The stable key of each item of the catalogue."""

    TORTILLA = "tortilla"
    PAELLA = "paella"
    PIZZA = "pizza"
    BURGER = "burger"
    SUSHI = "sushi"
    PASTA = "pasta"
    TACOS = "tacos"
    SALAD = "salad"
    BROCCOLI = "broccoli"
    STRAWBERRIES = "strawberries"
    ICE_CREAM = "ice_cream"
    CHOCOLATE = "chocolate"
    BALL = "ball"
    VIDEO_GAMES = "video_games"
    DANCE = "dance"
    READING = "reading"
    DRAWING = "drawing"
    PUZZLE = "puzzle"


_ACTIVITIES = frozenset(
    {
        ItemKey.BALL,
        ItemKey.VIDEO_GAMES,
        ItemKey.DANCE,
        ItemKey.READING,
        ItemKey.DRAWING,
        ItemKey.PUZZLE,
    }
)

# Every item and its kind. All free and unlimited in the v1.
CATALOG: Mapping[ItemKey, ItemKind] = MappingProxyType(
    {key: ItemKind.ACTIVITY if key in _ACTIVITIES else ItemKind.FOOD for key in ItemKey}
)


class Affinity(IntEnum):
    """How much a pet likes an item, from -2 to 2; what was never rated is neutral."""

    HATES = -2
    DISLIKES = -1
    NEUTRAL = 0
    LIKES = 1
    LOVES = 2


class InvalidItemError(TwochiError):
    """An item that does not fit the action: missing, unknown, of the other kind, or
    given to an action that takes none. An input error, never a refusal."""
