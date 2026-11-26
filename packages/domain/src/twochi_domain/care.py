"""Care actions: what the caretaker does from Casa, and how the engine decides them."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from statistics import fmean

from twochi_domain.catalog import CATALOG, Affinity, InvalidItemError, ItemKey, ItemKind
from twochi_domain.ids import UserId
from twochi_domain.needs import MAX_VALUE, MIN_VALUE, Need, NeedState, current_value
from twochi_domain.pet import SAD_FROM, Pet


class CareAction(StrEnum):
    """What the caretaker can do to their pet from the interface."""

    FEED = "feed"
    PLAY = "play"
    PET = "pet"
    BATHE = "bathe"
    SLEEP = "sleep"
    WAKE = "wake"


@dataclass(frozen=True, slots=True)
class Reaction:
    """How the pet took a food or an activity: the item and its affinity right then."""

    item: ItemKey
    affinity: Affinity


class SicknessChange(StrEnum):
    """An action that left the pet sick, or healed it; the event keeps it."""

    FELL_SICK = "fell_sick"
    HEALED = "healed"


@dataclass(frozen=True, slots=True)
class Applied:
    """The action took place: the pet after it and the change of each need it touched.

    `effective` is False only for a petting past the hourly limit, which applies with no
    effect; the limit counts the effective ones. `reaction` comes with feeding and
    playing; `sickness` when the action changed whether the pet is sick.
    """

    pet: Pet
    deltas: Mapping[Need, float]
    effective: bool = True
    reaction: Reaction | None = None
    sickness: SicknessChange | None = None


class Rejection(StrEnum):
    """Why the engine refused a care action; the front animates it."""

    NOT_CARETAKER = "not_caretaker"
    ASLEEP = "asleep"
    ALREADY_ASLEEP = "already_asleep"
    ALREADY_AWAKE = "already_awake"
    TOO_TIRED = "too_tired"


@dataclass(frozen=True, slots=True)
class Rejected:
    """The action did not take place, and why. Nothing about the pet changed."""

    reason: Rejection


type CareOutcome = Applied | Rejected


# Stored in every event, so a later change of a number never rewrites history. Bump it
# whenever a number below, a rate or a rejection rule changes.
RULES_VERSION = "2026-11-26"

# Starting numbers («Números de partida»). What a food adds to hunger and an activity
# to fun, by affinity; what the pet loves or likes adds affection on top.
FOOD_HUNGER: Mapping[Affinity, float] = {
    Affinity.HATES: 10.0,
    Affinity.DISLIKES: 20.0,
    Affinity.NEUTRAL: 30.0,
    Affinity.LIKES: 35.0,
    Affinity.LOVES: 45.0,
}
ACTIVITY_FUN: Mapping[Affinity, float] = {
    Affinity.HATES: 5.0,
    Affinity.DISLIKES: 15.0,
    Affinity.NEUTRAL: 25.0,
    Affinity.LIKES: 30.0,
    Affinity.LOVES: 40.0,
}
TASTE_AFFECTION: Mapping[Affinity, float] = {
    Affinity.LIKES: 5.0,
    Affinity.LOVES: 10.0,
}
PLAY_ENERGY = -8.0
PET_AFFECTION = 15.0
# Below this energy the pet is too tired to play.
MIN_PLAY_ENERGY = 10.0
# A sick pet heals only when every need is back to at least this.
HEALED_FROM = 40.0
# Pettings with effect allowed in the last hour; the next ones apply with no effect.
EFFECTIVE_PETS_PER_HOUR = 3
PETTING_WINDOW = timedelta(hours=1)


# The kind of item each action takes; the others take none.
_ITEM_KIND = {CareAction.FEED: ItemKind.FOOD, CareAction.PLAY: ItemKind.ACTIVITY}


def checked_item(action: CareAction, key: str | None) -> ItemKey | None:
    """The catalogue item `key` names if it fits `action`, or InvalidItemError.

    Feeding takes a food and playing an activity; every other action takes nothing.
    """
    kind = _ITEM_KIND.get(action)
    if key is None and kind is None:
        return None
    if key is None or key not in CATALOG or CATALOG[ItemKey(key)] is not kind:
        raise InvalidItemError
    return ItemKey(key)


def apply_care(
    pet: Pet,
    action: CareAction,
    *,
    item: ItemKey | None = None,
    affinity: Affinity = Affinity.NEUTRAL,
    actor: UserId,
    now: datetime,
    recent_effective_pets: int,
) -> CareOutcome:
    """Decide a care action at `now`: apply it or say why not.

    Feeding and playing take an `item` of their kind and the pet's `affinity` with it;
    an item that does not fit raises InvalidItemError, an input error. Anything else is
    an outcome, never an exception. The needs are first brought to their value at
    `now`, so switching between awake and asleep never rewrites the time already passed.
    """
    checked_item(action, item)
    before = _materialized(pet, now)
    reason = _rejection(pet, action, actor=actor, energy=before[Need.ENERGY])
    if reason is not None:
        return Rejected(reason)
    effective = True
    asleep = pet.asleep
    effects: dict[Need, float] = {}
    match action:
        case CareAction.FEED:
            effects[Need.HUNGER] = FOOD_HUNGER[affinity]
        case CareAction.PLAY:
            effects[Need.FUN] = ACTIVITY_FUN[affinity]
            effects[Need.ENERGY] = PLAY_ENERGY
        case CareAction.PET:
            effective = recent_effective_pets < EFFECTIVE_PETS_PER_HOUR
            effects[Need.AFFECTION] = PET_AFFECTION if effective else 0.0
        case CareAction.BATHE:
            effects[Need.HYGIENE] = MAX_VALUE - before[Need.HYGIENE]
        case CareAction.SLEEP:
            asleep = True
        case CareAction.WAKE:
            asleep = False
    if item is not None and affinity in TASTE_AFFECTION:
        effects[Need.AFFECTION] = TASTE_AFFECTION[affinity]
    after = dict(before)
    deltas: dict[Need, float] = {}
    for need, effect in effects.items():
        after[need] = _clamp(before[need] + effect)
        # The effect itself unless clamped: subtracting floats would add noise to it.
        clamped = after[need] != before[need] + effect
        deltas[need] = after[need] - before[need] if clamped else effect
    sick_since = _sick_since(pet.sick_since, before, after, now=now)
    return Applied(
        pet=replace(
            pet,
            needs={n: NeedState(value=v, updated_at=now) for n, v in after.items()},
            asleep=asleep,
            sick_since=sick_since,
        ),
        deltas=deltas,
        effective=effective,
        reaction=None if item is None else Reaction(item=item, affinity=affinity),
        sickness=_sickness_change(pet.sick_since, sick_since),
    )


def _rejection(
    pet: Pet, action: CareAction, *, actor: UserId, energy: float
) -> Rejection | None:
    # The order is part of the rule: the first reason that holds is the one given.
    if actor != pet.caretaker_user_id:
        return Rejection.NOT_CARETAKER
    if pet.asleep and action not in {CareAction.WAKE, CareAction.SLEEP}:
        return Rejection.ASLEEP
    if pet.asleep and action is CareAction.SLEEP:
        return Rejection.ALREADY_ASLEEP
    if not pet.asleep and action is CareAction.WAKE:
        return Rejection.ALREADY_AWAKE
    if action is CareAction.PLAY and energy < MIN_PLAY_ENERGY:
        return Rejection.TOO_TIRED
    return None


def _sick_since(
    since: datetime | None,
    before: Mapping[Need, float],
    after: Mapping[Need, float],
    *,
    now: datetime,
) -> datetime | None:
    # Only an action moves it; reading never writes. That holds because between two
    # actions the average does not rise, except asleep with needs already at 0.
    if since is None and fmean(before.values()) < SAD_FROM:
        since = now
    if since is not None and min(after.values()) >= HEALED_FROM:
        return None
    return since


def _sickness_change(
    before: datetime | None, after: datetime | None
) -> SicknessChange | None:
    if before is None and after is not None:
        return SicknessChange.FELL_SICK
    if before is not None and after is None:
        return SicknessChange.HEALED
    return None


def _materialized(pet: Pet, now: datetime) -> dict[Need, float]:
    return {
        need: current_value(need, state, now=now, asleep=pet.asleep)
        for need, state in pet.needs.items()
    }


def _clamp(value: float) -> float:
    return min(MAX_VALUE, max(MIN_VALUE, value))
