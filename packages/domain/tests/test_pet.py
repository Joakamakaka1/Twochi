from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from twochi_domain.errors import TwochiError
from twochi_domain.ids import CoupleId, PetId, UserId
from twochi_domain.needs import Need, NeedState
from twochi_domain.pet import Mood, Pet, read_pet

T0 = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
ALICE = UserId(UUID("00000000-0000-4000-8000-00000000000a"))
BRUNO = UserId(UUID("00000000-0000-4000-8000-00000000000b"))


def hours(n: float) -> timedelta:
    return timedelta(hours=n)


def pet(
    *,
    values: Mapping[Need, float] | None = None,
    asleep: bool = False,
    sick_since: datetime | None = None,
    updated_at: datetime = T0,
) -> Pet:
    """A pet that represents Alice and Bruno cares for; needs at 80 unless given."""
    given = values or {}
    return Pet(
        id=PetId(UUID("00000000-0000-4000-8000-0000000000f1")),
        couple_id=CoupleId(UUID("00000000-0000-4000-8000-0000000000c1")),
        represents_user_id=ALICE,
        caretaker_user_id=BRUNO,
        name="Ali",
        model_key="ali",
        needs={
            need: NeedState(value=given.get(need, 80), updated_at=updated_at)
            for need in Need
        },
        asleep=asleep,
        sick_since=sick_since,
    )


def test_reading_gives_each_need_at_now_with_its_awake_rate() -> None:
    reading = read_pet(pet(), now=T0 + hours(2))

    hunger = reading.needs[Need.HUNGER]
    assert hunger.value == 68
    assert hunger.updated_at == T0 + hours(2)
    assert hunger.rate_per_hour == -6
    assert reading.needs[Need.ENERGY].rate_per_hour == -5


@pytest.mark.parametrize(
    ("value", "mood"),
    [
        (100, Mood.HAPPY),
        (70, Mood.HAPPY),
        (69.9, Mood.NORMAL),
        (40, Mood.NORMAL),
        (39.9, Mood.SAD),
        (20, Mood.SAD),
        (19.9, Mood.SICK),
        (0, Mood.SICK),
    ],
)
def test_mood_follows_the_average_of_the_needs(value: float, mood: Mood) -> None:
    reading = read_pet(pet(values=dict.fromkeys(Need, value)), now=T0)

    assert reading.mood is mood


def test_the_average_decides_even_when_needs_differ() -> None:
    # (100 + 100 + 50 + 50 + 50) / 5 = 70
    values = {
        Need.HUNGER: 100,
        Need.ENERGY: 100,
        Need.HYGIENE: 50,
        Need.FUN: 50,
        Need.AFFECTION: 50,
    }

    assert read_pet(pet(values=values), now=T0).mood is Mood.HAPPY


def test_a_need_below_ten_caps_the_mood_at_sad() -> None:
    # Average 81.8, but fun is almost empty.
    values = {
        Need.FUN: 9,
        Need.HUNGER: 100,
        Need.ENERGY: 100,
        Need.HYGIENE: 100,
        Need.AFFECTION: 100,
    }

    assert read_pet(pet(values=values), now=T0).mood is Mood.SAD


def test_a_need_at_ten_does_not_cap_the_mood() -> None:
    values = {
        Need.FUN: 10,
        Need.HUNGER: 100,
        Need.ENERGY: 100,
        Need.HYGIENE: 100,
        Need.AFFECTION: 100,
    }

    assert read_pet(pet(values=values), now=T0).mood is Mood.HAPPY


def test_a_pet_marked_sick_stays_sick_while_its_average_is_back_up() -> None:
    reading = read_pet(pet(sick_since=T0 - hours(3)), now=T0)

    assert reading.mood is Mood.SICK


def test_the_mood_is_read_at_now_not_at_the_last_update() -> None:
    # 80 at T0; ten hours awake later the average is (20 + 30 + 50 + 10 + 40) / 5 = 30.
    reading = read_pet(pet(), now=T0 + hours(10))

    assert reading.mood is Mood.SAD


def test_reading_an_asleep_pet_gives_asleep_rates() -> None:
    reading = read_pet(pet(asleep=True), now=T0 + hours(1))

    assert reading.asleep
    assert reading.needs[Need.ENERGY].value == 92
    assert reading.needs[Need.ENERGY].rate_per_hour == 12
    assert reading.needs[Need.HUNGER].rate_per_hour == -3


def test_a_pet_without_all_five_needs_is_rejected() -> None:
    complete = pet()
    missing_fun = {n: s for n, s in complete.needs.items() if n is not Need.FUN}

    with pytest.raises(TwochiError):
        replace(complete, needs=missing_fun)
