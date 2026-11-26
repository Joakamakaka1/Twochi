"""Invariants the schema itself guards, whoever writes."""

from uuid import uuid4

import pytest
from conftest import Couples, TestCouple

pytestmark = pytest.mark.anyio


async def add_event(couples: Couples, couple: TestCouple, key: str) -> None:
    await couples.admin.execute(
        "insert into app.pet_events "
        "(couple_id, pet_id, source, action, rules_version, idempotency_key) "
        "values ($1, $2, 'system', 'test', 'test', $3)",
        couple.id,
        couple.pet_of_alice.id,
        key,
    )


async def test_a_person_cares_for_one_pet_only(couples: Couples) -> None:
    couple = await couples.create()
    third = uuid4()
    await couples.admin.execute(
        "insert into auth.users (id, email, aud, role) "
        "values ($1, $2, 'authenticated', 'authenticated')",
        third,
        f"{third}@twochi.test",
    )
    await couples.admin.execute(
        "insert into app.profiles (user_id, couple_id, display_name) "
        "values ($1, $2, 'Carla')",
        third,
        couple.id,
    )

    # Bruno already cares for Alice's pet: a second pet in his care is refused.
    with pytest.raises(Exception, match="duplicate key"):
        await couples.admin.execute(
            "insert into app.pets "
            "(couple_id, represents_user_id, caretaker_user_id, name, model_key) "
            "values ($1, $2, $3, 'Car', 'placeholder')",
            couple.id,
            third,
            couple.bruno,
        )


async def test_two_couples_may_use_the_same_idempotency_key(couples: Couples) -> None:
    ours = await couples.create()
    theirs = await couples.create()

    await add_event(couples, ours, "same-key")
    await add_event(couples, theirs, "same-key")


async def test_one_pet_never_repeats_an_idempotency_key(couples: Couples) -> None:
    couple = await couples.create()
    await add_event(couples, couple, "once")

    with pytest.raises(Exception, match="duplicate key"):
        await add_event(couples, couple, "once")


@pytest.mark.parametrize("affinity", [-3, 3])
async def test_an_affinity_stays_between_minus_two_and_two(
    couples: Couples, affinity: int
) -> None:
    couple = await couples.create()

    with pytest.raises(Exception, match="check constraint"):
        await couples.admin.execute(
            "insert into app.item_affinities (couple_id, pet_id, item_key, affinity) "
            "values ($1, $2, 'pizza', $3)",
            couple.id,
            couple.pet_of_alice.id,
            affinity,
        )


async def test_a_pet_has_one_affinity_per_item(couples: Couples) -> None:
    couple = await couples.create()
    insert = (
        "insert into app.item_affinities (couple_id, pet_id, item_key, affinity) "
        "values ($1, $2, 'pizza', 1)"
    )
    await couples.admin.execute(insert, couple.id, couple.pet_of_alice.id)

    with pytest.raises(Exception, match="duplicate key"):
        await couples.admin.execute(insert, couple.id, couple.pet_of_alice.id)


async def test_a_taste_belongs_to_a_pet_of_its_own_couple(couples: Couples) -> None:
    ours = await couples.create()
    theirs = await couples.create()

    with pytest.raises(Exception, match="foreign key"):
        await couples.admin.execute(
            "insert into app.item_affinities (couple_id, pet_id, item_key, affinity) "
            "values ($1, $2, 'pizza', 1)",
            ours.id,
            theirs.pet_of_alice.id,
        )
