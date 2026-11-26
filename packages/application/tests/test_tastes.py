"""`get_my_tastes` and `rate_taste` against local Supabase with real RLS; only the clock
is fake. Each person rates the pet that represents them, never the one they care for,
and no use case shows the caretaker the list (ADR 0015)."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from conftest import API_URL, Couples, TestCouple

from twochi_application.actors import UserActor
from twochi_application.care import ApplyCareAction, apply_care_action
from twochi_application.tastes import (
    MyTastes,
    NoPetYetError,
    RatedTaste,
    RateTaste,
    get_my_tastes,
    rate_taste,
)
from twochi_application.testing import FixedClock
from twochi_data.database import PostgresDatabase
from twochi_domain.care import CareAction, Reaction
from twochi_domain.catalog import ActivityKey, Affinity, FoodKey, ItemKey
from twochi_domain.needs import Need

pytestmark = pytest.mark.anyio

T0 = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
async def db() -> AsyncIterator[PostgresDatabase]:
    database = PostgresDatabase(API_URL, require_tls=False)
    try:
        yield database
    finally:
        await database.close()


async def rate(
    db: PostgresDatabase, actor: UserActor, item: ItemKey, affinity: Affinity
) -> RatedTaste:
    command = RateTaste(actor=actor, item=item, affinity=affinity)
    return await rate_taste(command, db=db, clock=FixedClock(T0))


async def tastes_of(db: PostgresDatabase, actor: UserActor) -> MyTastes:
    return await get_my_tastes(actor, db=db)


async def test_a_person_rates_the_pet_that_represents_them(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create()
    alice = couple.actor(couple.alice)

    rated = await rate(db, alice, FoodKey.PIZZA, Affinity.LOVES)

    assert rated == RatedTaste(
        pet_id=couple.pet_of_alice.id, item=FoodKey.PIZZA, affinity=Affinity.LOVES
    )
    assert await tastes_of(db, alice) == MyTastes(
        pet_id=couple.pet_of_alice.id, tastes={FoodKey.PIZZA: Affinity.LOVES}
    )


async def test_rating_never_touches_the_pet_you_care_for(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create()

    await rate(db, couple.actor(couple.alice), ActivityKey.DANCE, Affinity.HATES)

    # Alice cares for Bruno's pet: its tastes are still Bruno's, and still none.
    assert await tastes_of(db, couple.actor(couple.bruno)) == MyTastes(
        pet_id=couple.pet_of_bruno.id, tastes={}
    )


async def test_only_what_was_rated_is_listed(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create()

    tastes = await tastes_of(db, couple.actor(couple.alice))

    assert tastes == MyTastes(pet_id=couple.pet_of_alice.id, tastes={})


async def test_rating_again_replaces_the_taste(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create()
    alice = couple.actor(couple.alice)
    await rate(db, alice, FoodKey.SUSHI, Affinity.LOVES)
    await rate(db, alice, ActivityKey.BALL, Affinity.LIKES)

    await rate(db, alice, FoodKey.SUSHI, Affinity.DISLIKES)

    assert (await tastes_of(db, alice)).tastes == {
        FoodKey.SUSHI: Affinity.DISLIKES,
        ActivityKey.BALL: Affinity.LIKES,
    }


async def test_two_ratings_of_the_same_item_at_once_both_land(
    couples: Couples,
) -> None:
    couple = await couples.create()
    alice = couple.actor(couple.alice)
    first = PostgresDatabase(API_URL, require_tls=False)
    second = PostgresDatabase(API_URL, require_tls=False)
    try:
        await asyncio.gather(
            rate(first, alice, FoodKey.PASTA, Affinity.LIKES),
            rate(second, alice, FoodKey.PASTA, Affinity.LIKES),
        )
        tastes = await tastes_of(first, alice)
    finally:
        await first.close()
        await second.close()

    assert tastes.tastes == {FoodKey.PASTA: Affinity.LIKES}


async def test_a_taste_rated_changes_what_caring_gives(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(
        needs_of_alices_pet=dict.fromkeys(Need, 50), updated_at=T0
    )
    await rate(db, couple.actor(couple.alice), FoodKey.PIZZA, Affinity.LOVES)

    # Bruno, who cares for Alice's pet, gives it pizza.
    fed = await apply_care_action(
        ApplyCareAction(
            actor=couple.actor(couple.bruno),
            pet_id=couple.pet_of_alice.id,
            action=CareAction.FEED,
            idempotency_key=str(uuid4()),
            item_key=FoodKey.PIZZA,
        ),
        db=db,
        clock=FixedClock(T0),
    )

    assert fed.reaction == Reaction(item=FoodKey.PIZZA, affinity=Affinity.LOVES)
    assert fed.deltas == {Need.HUNGER: 45, Need.AFFECTION: 10}


async def test_before_the_pet_is_born_there_is_nothing_to_rate(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(with_pets=False)
    alice = couple.actor(couple.alice)

    assert await tastes_of(db, alice) == MyTastes(pet_id=None, tastes={})
    with pytest.raises(NoPetYetError):
        await rate(db, alice, FoodKey.PIZZA, Affinity.LOVES)


async def test_a_key_the_catalogue_no_longer_holds_is_ignored(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create()
    await couples.admin.execute(
        "insert into app.item_affinities (couple_id, pet_id, item_key, affinity) "
        "values ($1, $2, 'caviar', 2)",
        couple.id,
        couple.pet_of_alice.id,
    )

    tastes = await tastes_of(db, couple.actor(couple.alice))

    assert tastes.tastes == {}


async def two_couples_with_a_taste(
    couples: Couples, db: PostgresDatabase
) -> tuple[TestCouple, TestCouple]:
    ours = await couples.create()
    theirs = await couples.create()
    await rate(db, ours.actor(ours.alice), FoodKey.TACOS, Affinity.LOVES)
    return ours, theirs


async def test_another_couple_neither_reads_nor_writes_our_tastes(
    couples: Couples, db: PostgresDatabase
) -> None:
    ours, theirs = await two_couples_with_a_taste(couples, db)
    # A forged mix: our Alice's id with the other couple's claim.
    intruder = theirs.actor(ours.alice)

    assert await tastes_of(db, intruder) == MyTastes(pet_id=None, tastes={})
    with pytest.raises(NoPetYetError):
        await rate(db, intruder, FoodKey.TACOS, Affinity.HATES)
    assert (await tastes_of(db, theirs.actor(theirs.alice))).tastes == {}
    assert (await tastes_of(db, ours.actor(ours.alice))).tastes == {
        FoodKey.TACOS: Affinity.LOVES
    }


async def test_a_token_without_the_second_factor_neither_reads_nor_writes(
    couples: Couples, db: PostgresDatabase
) -> None:
    ours, _theirs = await two_couples_with_a_taste(couples, db)
    without_second_factor = ours.actor(ours.alice, aal="aal1")

    assert await tastes_of(db, without_second_factor) == MyTastes(
        pet_id=None, tastes={}
    )
    with pytest.raises(NoPetYetError):
        await rate(db, without_second_factor, FoodKey.TACOS, Affinity.HATES)
    assert (await tastes_of(db, ours.actor(ours.alice))).tastes == {
        FoodKey.TACOS: Affinity.LOVES
    }
