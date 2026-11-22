"""The pet as the engine sees it, and how it reads at a given moment."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from statistics import fmean

from twochi_domain.errors import TwochiError
from twochi_domain.ids import CoupleId, PetId, UserId
from twochi_domain.needs import Need, NeedState, current_value, rate_per_hour


@dataclass(frozen=True, slots=True)
class Pet:
    """A pet and its five needs: it represents one person; the other cares for it."""

    id: PetId
    couple_id: CoupleId
    represents_user_id: UserId
    caretaker_user_id: UserId
    name: str
    model_key: str
    needs: Mapping[Need, NeedState]
    asleep: bool
    sick_since: datetime | None

    def __post_init__(self) -> None:
        if set(self.needs) != set(Need):
            raise IncompleteNeedsError(sorted(set(Need) - set(self.needs)))


class IncompleteNeedsError(TwochiError):
    """A pet reached the engine without all five of its needs."""


@dataclass(frozen=True, slots=True)
class NeedReading:
    """A need at a moment and its hourly change, for the front to interpolate."""

    value: float
    updated_at: datetime
    rate_per_hour: float


class Mood(StrEnum):
    """What the pet shows, from the average of its needs."""

    HAPPY = "happy"
    NORMAL = "normal"
    SAD = "sad"
    SICK = "sick"


# Starting numbers («Números de partida»); they move to the versioned catalogue.
HAPPY_FROM = 70.0
NORMAL_FROM = 40.0
SAD_FROM = 20.0
# Any need below this leaves the pet sad at best, whatever the average.
SAD_FLOOR = 10.0
# A pet is born awake with every need here. The signup trigger writes it in SQL; a test
# of the births keeps the two in step.
BIRTH_NEED_VALUE = 80.0


@dataclass(frozen=True, slots=True)
class PetReading:
    """A pet as it is at `now`."""

    pet: Pet
    needs: Mapping[Need, NeedReading]
    asleep: bool
    mood: Mood


def read_pet(pet: Pet, *, now: datetime) -> PetReading:
    """Read each need at `now` with the rate its sleep state gives, and the mood."""
    needs = {
        need: NeedReading(
            value=current_value(need, state, now=now, asleep=pet.asleep),
            updated_at=now,
            rate_per_hour=rate_per_hour(need, asleep=pet.asleep),
        )
        for need, state in pet.needs.items()
    }
    values = [reading.value for reading in needs.values()]
    mood = _mood(values, marked_sick=pet.sick_since is not None)
    return PetReading(pet=pet, needs=needs, asleep=pet.asleep, mood=mood)


def _mood(values: list[float], *, marked_sick: bool) -> Mood:
    average = fmean(values)
    if marked_sick or average < SAD_FROM:
        return Mood.SICK
    if min(values) < SAD_FLOOR or average < NORMAL_FROM:
        return Mood.SAD
    return Mood.HAPPY if average >= HAPPY_FROM else Mood.NORMAL
