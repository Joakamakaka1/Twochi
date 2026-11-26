"""The catalogue: the foods and activities a caretaker may choose, and the tastes.

The catalogue is versioned with the rules of the game (`RULES_VERSION`). Names and
icons are interface, so they live in the front, keyed by these stable keys. The kind
of an item is its type: a food is a `FoodKey`, an activity an `ActivityKey`.
"""

from enum import IntEnum, StrEnum

from twochi_domain.errors import TwochiError


class FoodKey(StrEnum):
    """A food: given in the kitchen, it raises hunger."""

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


class ActivityKey(StrEnum):
    """An activity: played in the living room, it raises fun."""

    BALL = "ball"
    VIDEO_GAMES = "video_games"
    DANCE = "dance"
    READING = "reading"
    DRAWING = "drawing"
    PUZZLE = "puzzle"


# Every item of the catalogue, all free and unlimited in the v1.
type ItemKey = FoodKey | ActivityKey


def item_key(value: str) -> ItemKey | None:
    """The item a stored key names, or None if the catalogue no longer holds it."""
    if value in FoodKey:
        return FoodKey(value)
    if value in ActivityKey:
        return ActivityKey(value)
    return None


class Affinity(IntEnum):
    """How much a pet likes an item, from -2 to 2; what was never rated is neutral."""

    HATES = -2
    DISLIKES = -1
    NEUTRAL = 0
    LIKES = 1
    LOVES = 2


class InvalidItemError(TwochiError):
    """An item that does not fit the action: missing, of the other kind, or given to
    an action that takes none. An input error, never a refusal."""
