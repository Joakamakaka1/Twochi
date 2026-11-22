"""`get_home` against local Supabase with real RLS; the clock is the only double."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from conftest import API_URL, Couples

from twochi_application.home import get_home
from twochi_application.testing import FixedClock
from twochi_data.database import PostgresDatabase
from twochi_domain.needs import Need
from twochi_domain.pet import Mood

pytestmark = pytest.mark.anyio

T0 = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


@pytest.fixture
async def db() -> AsyncIterator[PostgresDatabase]:
    database = PostgresDatabase(API_URL)
    try:
        yield database
    finally:
        await database.close()


async def test_home_shows_the_pet_the_person_cares_for(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)

    home = await get_home(
        couple.actor(couple.bruno), db=db, clock=FixedClock(T0 + timedelta(hours=1))
    )

    assert home.pet is not None
    assert home.pet.pet.id == couple.pet_of_alice.id
    assert home.pet.pet.name == "Ali"
    assert home.pet.needs[Need.HUNGER].value == 74
    assert home.pet.needs[Need.HUNGER].rate_per_hour == -6
    assert home.pet.mood is Mood.HAPPY


async def test_each_person_sees_the_other_ones_pet(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)

    home = await get_home(couple.actor(couple.alice), db=db, clock=FixedClock(T0))

    assert home.pet is not None
    assert home.pet.pet.id == couple.pet_of_bruno.id


async def test_home_reads_the_stored_needs(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(needs_of_alices_pet={Need.FUN: 5}, updated_at=T0)

    home = await get_home(couple.actor(couple.bruno), db=db, clock=FixedClock(T0))

    assert home.pet is not None
    assert home.pet.needs[Need.FUN].value == 5
    assert home.pet.mood is Mood.SAD


async def test_home_has_no_pet_before_both_people_arrive(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(with_pets=False)

    home = await get_home(couple.actor(couple.bruno), db=db, clock=FixedClock(T0))

    assert home.pet is None


async def test_a_token_from_another_couple_never_sees_this_pet(
    couples: Couples, db: PostgresDatabase
) -> None:
    ours = await couples.create()
    theirs = await couples.create()
    # A forged mix: our caretaker's id with the other couple's claim.
    intruder = theirs.actor(ours.bruno)

    home = await get_home(intruder, db=db, clock=FixedClock(T0))

    assert home.pet is None


async def test_a_token_without_the_second_factor_sees_nothing(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create()

    home = await get_home(
        couple.actor(couple.bruno, aal="aal1"), db=db, clock=FixedClock(T0)
    )

    assert home.pet is None
