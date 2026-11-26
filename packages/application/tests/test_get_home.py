"""`get_home` against local Supabase with real RLS; the clock is the only double."""

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import API_URL, Couples, TestCouple

from twochi_application.care import ApplyCareAction, apply_care_action
from twochi_application.home import get_home
from twochi_application.tastes import RateTaste, rate_taste
from twochi_application.testing import FixedClock
from twochi_data.database import PostgresDatabase
from twochi_domain.care import CareAction
from twochi_domain.catalog import ActivityKey, Affinity, FoodKey, ItemKey
from twochi_domain.ids import UserId
from twochi_domain.needs import Need
from twochi_domain.pet import Mood

pytestmark = pytest.mark.anyio

T0 = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


@pytest.fixture
async def db() -> AsyncIterator[PostgresDatabase]:
    database = PostgresDatabase(API_URL, require_tls=False)
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


# Gustos descubiertos: what the caretaker saw the last time they gave each item.


async def alice_rates(
    db: PostgresDatabase, couple: TestCouple, item: ItemKey, affinity: Affinity
) -> None:
    command = RateTaste(actor=couple.actor(couple.alice), item=item, affinity=affinity)
    await rate_taste(command, db=db, clock=FixedClock(T0))


async def bruno_gives(
    db: PostgresDatabase, couple: TestCouple, action: CareAction, item: ItemKey
) -> None:
    """Bruno, the caretaker, gives an item to the pet that represents Alice."""
    command = ApplyCareAction(
        actor=couple.actor(couple.bruno),
        pet_id=couple.pet_of_alice.id,
        action=action,
        idempotency_key=str(uuid4()),
        item_key=item,
    )
    await apply_care_action(command, db=db, clock=FixedClock(T0))


async def discovered_by(
    db: PostgresDatabase, couple: TestCouple, user: UserId
) -> Mapping[ItemKey, Affinity]:
    home = await get_home(couple.actor(user), db=db, clock=FixedClock(T0))
    return home.discovered


async def test_nothing_is_discovered_before_it_is_given(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    await alice_rates(db, couple, FoodKey.PIZZA, Affinity.LOVES)

    assert await discovered_by(db, couple, couple.bruno) == {}


async def test_giving_an_item_discovers_the_reaction_seen(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    await alice_rates(db, couple, FoodKey.PIZZA, Affinity.LOVES)
    await alice_rates(db, couple, ActivityKey.DANCE, Affinity.HATES)

    await bruno_gives(db, couple, CareAction.FEED, FoodKey.PIZZA)
    await bruno_gives(db, couple, CareAction.PLAY, ActivityKey.DANCE)
    await bruno_gives(db, couple, CareAction.FEED, FoodKey.SALAD)

    assert await discovered_by(db, couple, couple.bruno) == {
        FoodKey.PIZZA: Affinity.LOVES,
        ActivityKey.DANCE: Affinity.HATES,
        FoodKey.SALAD: Affinity.NEUTRAL,
    }


async def test_a_changed_taste_shows_only_once_it_is_given_again(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    await alice_rates(db, couple, FoodKey.SUSHI, Affinity.LOVES)
    await bruno_gives(db, couple, CareAction.FEED, FoodKey.SUSHI)

    await alice_rates(db, couple, FoodKey.SUSHI, Affinity.HATES)
    seen_before = await discovered_by(db, couple, couple.bruno)
    # At the same moment, as the clock is fixed: the one given last is what counts.
    await bruno_gives(db, couple, CareAction.FEED, FoodKey.SUSHI)

    assert seen_before == {FoodKey.SUSHI: Affinity.LOVES}
    assert await discovered_by(db, couple, couple.bruno) == {
        FoodKey.SUSHI: Affinity.HATES
    }


async def test_the_tastes_discovered_are_those_of_the_pet_you_care_for(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    await bruno_gives(db, couple, CareAction.FEED, FoodKey.TACOS)

    # Alice cares for Bruno's pet, which was given nothing.
    assert await discovered_by(db, couple, couple.alice) == {}


async def test_another_couple_discovers_nothing_of_ours(
    couples: Couples, db: PostgresDatabase
) -> None:
    ours = await couples.create(updated_at=T0)
    theirs = await couples.create(updated_at=T0)
    await bruno_gives(db, ours, CareAction.FEED, FoodKey.TACOS)
    # A forged mix: our caretaker's id with the other couple's claim.
    intruder = theirs.actor(ours.bruno)

    home = await get_home(intruder, db=db, clock=FixedClock(T0))

    assert home.discovered == {}
    assert await discovered_by(db, theirs, theirs.bruno) == {}


async def test_an_item_the_catalogue_no_longer_holds_is_ignored(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    await bruno_gives(db, couple, CareAction.FEED, FoodKey.PASTA)
    await couples.admin.execute(
        "insert into app.pet_events (couple_id, pet_id, actor_user_id, source, action,"
        " payload, rules_version, idempotency_key, created_at)"
        " values ($1, $2, $3, 'ui', 'feed', $4::jsonb, 'old', $5, $6)",
        couple.id,
        couple.pet_of_alice.id,
        couple.bruno,
        '{"item_key": "caviar", "affinity": 2, "effective": true}',
        str(uuid4()),
        T0,
    )

    assert await discovered_by(db, couple, couple.bruno) == {
        FoodKey.PASTA: Affinity.NEUTRAL
    }
