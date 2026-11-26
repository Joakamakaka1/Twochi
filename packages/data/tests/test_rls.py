"""RLS and roles straight in SQL, as the browser's token would reach them."""

import json
from collections.abc import Mapping
from uuid import UUID

import pytest
from conftest import ADMIN_URL, API_URL, Couples, TestCouple

from twochi_data.sql import Connection, bool_at, connect, text_at

pytestmark = pytest.mark.anyio

TABLES = ["couples", "profiles", "pets", "pet_needs", "pet_events", "item_affinities"]

# Local Supabase's superuser (fixed local credentials, never a deployed database).
SUPERUSER_URL = ADMIN_URL.replace("postgres:postgres@", "supabase_admin:postgres@", 1)


async def scalar(connection: Connection, query: str, *args: object) -> object:
    rows = await connection.fetch(query, *args)
    return rows[0]["value"]


async def as_authenticated(
    claims: Mapping[str, object], query: str, *args: object
) -> object:
    """Run one query as a browser token would: role `authenticated` with `claims`."""
    connection = await connect(ADMIN_URL)
    try:
        async with connection.transaction():
            await connection.execute("set local role authenticated")
            await connection.execute(
                "select set_config('request.jwt.claims', $1, true)",
                json.dumps(dict(claims)),
            )
            return await scalar(connection, query, *args)
    finally:
        await connection.close()


async def visible_rows(couple: TestCouple, table: str, *, aal: str) -> object:
    claims = couple.actor(couple.bruno, aal=aal).claims
    return await as_authenticated(
        claims,
        f"select count(*) as value from app.{table}",  # noqa: S608 - fixed table names
    )


async def add_event(couples: Couples, couple: TestCouple) -> None:
    """An event and a taste on Alice's pet, so every table has a row of the couple."""
    await couples.admin.execute(
        "insert into app.pet_events "
        "(couple_id, pet_id, source, action, rules_version, idempotency_key) "
        "values ($1, $2, 'system', 'birth', 'test', $3)",
        couple.id,
        couple.pet_of_alice.id,
        f"birth:{couple.pet_of_alice.id}",
    )
    await couples.admin.execute(
        "insert into app.item_affinities (couple_id, pet_id, item_key, affinity) "
        "values ($1, $2, 'pizza', 2)",
        couple.id,
        couple.pet_of_alice.id,
    )


@pytest.mark.parametrize("table", TABLES)
async def test_a_second_factor_token_reads_its_couple(
    couples: Couples, table: str
) -> None:
    couple = await couples.create()
    await add_event(couples, couple)

    assert await visible_rows(couple, table, aal="aal2") != 0


@pytest.mark.parametrize("table", TABLES)
async def test_a_token_without_the_second_factor_reads_nothing(
    couples: Couples, table: str
) -> None:
    couple = await couples.create()
    await add_event(couples, couple)

    assert await visible_rows(couple, table, aal="aal1") == 0


@pytest.mark.parametrize("table", TABLES)
async def test_a_couple_never_reads_another_couples_rows(
    couples: Couples, table: str
) -> None:
    ours = await couples.create()
    theirs = await couples.create()
    await add_event(couples, theirs)
    column = "id" if table == "couples" else "couple_id"

    leaked = await as_authenticated(
        ours.actor(ours.bruno).claims,
        f"select count(*) as value from app.{table} where {column} = $1",  # noqa: S608 - fixed names
        theirs.id,
    )

    assert leaked == 0


async def test_the_api_role_reads_nothing_without_switching_role(
    couples: Couples,
) -> None:
    await couples.create()
    connection = await connect(API_URL)
    try:
        with pytest.raises(Exception, match="permission denied for schema app"):
            await connection.fetch("select count(*) from app.pets")
    finally:
        await connection.close()


async def test_the_api_role_cannot_bypass_rls() -> None:
    connection = await connect(ADMIN_URL)
    try:
        rows = await connection.fetch(
            "select rolbypassrls, rolsuper, rolinherit from pg_roles "
            "where rolname = 'twochi_api'"
        )
    finally:
        await connection.close()

    flags = rows[0]
    assert not bool_at(flags, "rolbypassrls")
    assert not bool_at(flags, "rolsuper")
    assert not bool_at(flags, "rolinherit")


async def call_hook(user: UUID) -> object:
    event = {"user_id": str(user), "claims": {"aal": "aal2", "couple_id": "stale"}}
    # Supabase Auth runs the hook as supabase_auth_admin: its grants are what is under
    # test. Only the local superuser may switch to that role.
    connection = await connect(SUPERUSER_URL)
    try:
        async with connection.transaction():
            await connection.execute("set local role supabase_auth_admin")
            rows = await connection.fetch(
                "select app.custom_access_token_hook($1::jsonb)::text as event",
                json.dumps(event),
            )
    finally:
        await connection.close()
    return json.loads(text_at(rows[0], "event"))["claims"]


async def test_the_token_hook_adds_the_persons_couple(couples: Couples) -> None:
    couple = await couples.create()

    assert await call_hook(couple.alice) == {"aal": "aal2", "couple_id": str(couple.id)}


async def test_the_token_hook_drops_the_claim_for_someone_without_a_couple() -> None:
    stranger = UUID("00000000-0000-4000-8000-00000000dead")

    assert await call_hook(stranger) == {"aal": "aal2"}


# Writes: only what the engine writes, by couple and with the second factor.

UPDATE_NEED = """
with changed as (
  update app.pet_needs set value = 50, updated_at = now()
  where pet_id = $1 and need = 'hunger'
  returning 1
)
select count(*) as value from changed
"""

UPDATE_PET = """
with changed as (
  update app.pets set asleep = true where id = $1 returning 1
)
select count(*) as value from changed
"""

INSERT_EVENT = """
with added as (
  insert into app.pet_events
    (couple_id, pet_id, actor_user_id, source, action, rules_version, idempotency_key)
  values ($1, $2, $3, 'ui', 'feed', 'test', gen_random_uuid()::text)
  returning 1
)
select count(*) as value from added
"""


@pytest.mark.parametrize("query", [UPDATE_NEED, UPDATE_PET], ids=["needs", "pets"])
async def test_a_second_factor_token_updates_its_couples_pets(
    couples: Couples, query: str
) -> None:
    couple = await couples.create()

    changed = await as_authenticated(
        couple.actor(couple.bruno).claims, query, couple.pet_of_alice.id
    )

    assert changed == 1


@pytest.mark.parametrize("query", [UPDATE_NEED, UPDATE_PET], ids=["needs", "pets"])
async def test_a_token_without_the_second_factor_updates_nothing(
    couples: Couples, query: str
) -> None:
    couple = await couples.create()

    changed = await as_authenticated(
        couple.actor(couple.bruno, aal="aal1").claims, query, couple.pet_of_alice.id
    )

    assert changed == 0


@pytest.mark.parametrize("query", [UPDATE_NEED, UPDATE_PET], ids=["needs", "pets"])
async def test_a_couple_never_updates_another_couples_pets(
    couples: Couples, query: str
) -> None:
    ours = await couples.create()
    theirs = await couples.create()

    changed = await as_authenticated(
        ours.actor(ours.bruno).claims, query, theirs.pet_of_alice.id
    )

    assert changed == 0


async def test_a_second_factor_token_records_its_own_event(couples: Couples) -> None:
    couple = await couples.create()

    added = await as_authenticated(
        couple.actor(couple.bruno).claims,
        INSERT_EVENT,
        couple.id,
        couple.pet_of_alice.id,
        couple.bruno,
    )

    assert added == 1


async def test_a_token_without_the_second_factor_records_no_event(
    couples: Couples,
) -> None:
    couple = await couples.create()

    with pytest.raises(Exception, match="row-level security"):
        await as_authenticated(
            couple.actor(couple.bruno, aal="aal1").claims,
            INSERT_EVENT,
            couple.id,
            couple.pet_of_alice.id,
            couple.bruno,
        )


async def test_a_couple_never_records_events_on_another_couples_pet(
    couples: Couples,
) -> None:
    ours = await couples.create()
    theirs = await couples.create()

    with pytest.raises(Exception, match="row-level security"):
        await as_authenticated(
            ours.actor(ours.bruno).claims,
            INSERT_EVENT,
            theirs.id,
            theirs.pet_of_alice.id,
            ours.bruno,
        )


async def test_nobody_records_an_event_in_someone_elses_name(
    couples: Couples,
) -> None:
    couple = await couples.create()

    with pytest.raises(Exception, match="row-level security"):
        await as_authenticated(
            couple.actor(couple.bruno).claims,
            INSERT_EVENT,
            couple.id,
            couple.pet_of_alice.id,
            couple.alice,
        )


# What `authenticated` may do on each table: reads, plus the engine's writes. Nothing
# deletes, and couples and profiles are never written from a person's token.
GRANTS = {
    "couples": {"SELECT"},
    "profiles": {"SELECT"},
    "pets": {"SELECT", "UPDATE"},
    "pet_needs": {"SELECT", "UPDATE"},
    "pet_events": {"SELECT", "INSERT"},
    "item_affinities": {"SELECT", "INSERT", "UPDATE"},
}

PRIVILEGES = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]


@pytest.mark.parametrize("table", TABLES)
async def test_authenticated_holds_only_the_engines_privileges(table: str) -> None:
    connection = await connect(ADMIN_URL)
    try:
        held = {
            privilege
            for privilege in PRIVILEGES
            if await scalar(
                connection,
                # A column grant counts too; deletes and truncates have no columns.
                "select case when $2 in ('DELETE', 'TRUNCATE') "
                "  then has_table_privilege('authenticated', $1, $2) "
                "  else has_any_column_privilege('authenticated', $1, $2) "
                "end as value",
                f"app.{table}",
                privilege,
            )
        }
    finally:
        await connection.close()

    assert held == GRANTS[table]


UPDATABLE_COLUMNS = {
    "pets": {"asleep", "sick_since"},
    "pet_needs": {"value", "updated_at"},
    "item_affinities": {"affinity", "updated_at"},
}


@pytest.mark.parametrize("table", sorted(UPDATABLE_COLUMNS))
async def test_the_engine_updates_only_the_state_it_owns(table: str) -> None:
    connection = await connect(ADMIN_URL)
    try:
        rows = await connection.fetch(
            "select column_name::text as name from information_schema.columns "
            "where table_schema = 'app' and table_name = $1 "
            "and has_column_privilege('authenticated', "
            "  format('app.%I', table_name), column_name, 'UPDATE')",
            table,
        )
    finally:
        await connection.close()

    assert {text_at(row, "name") for row in rows} == UPDATABLE_COLUMNS[table]


# Tastes (ADR 0015): both people read them, only the person a pet represents writes.

RATE = """
with rated as (
  insert into app.item_affinities (couple_id, pet_id, item_key, affinity)
  values ($1, $2, 'sushi', -2)
  returning 1
)
select count(*) as value from rated
"""

RERATE = """
with rated as (
  update app.item_affinities set affinity = 1, updated_at = now()
  where pet_id = $1 and item_key = 'pizza'
  returning 1
)
select count(*) as value from rated
"""


async def test_a_person_rates_the_pet_that_represents_them(couples: Couples) -> None:
    couple = await couples.create()

    rated = await as_authenticated(
        couple.actor(couple.alice).claims, RATE, couple.id, couple.pet_of_alice.id
    )

    assert rated == 1


async def test_the_caretaker_never_rates_the_pet_they_care_for(
    couples: Couples,
) -> None:
    couple = await couples.create()

    with pytest.raises(Exception, match="row-level security"):
        await as_authenticated(
            couple.actor(couple.bruno).claims, RATE, couple.id, couple.pet_of_alice.id
        )


async def test_a_person_changes_a_taste_of_the_pet_that_represents_them(
    couples: Couples,
) -> None:
    couple = await couples.create()
    await add_event(couples, couple)

    changed = await as_authenticated(
        couple.actor(couple.alice).claims, RERATE, couple.pet_of_alice.id
    )

    assert changed == 1


async def test_the_caretaker_never_changes_a_taste(couples: Couples) -> None:
    couple = await couples.create()
    await add_event(couples, couple)

    changed = await as_authenticated(
        couple.actor(couple.bruno).claims, RERATE, couple.pet_of_alice.id
    )

    assert changed == 0


async def test_a_token_without_the_second_factor_rates_nothing(
    couples: Couples,
) -> None:
    couple = await couples.create()
    await add_event(couples, couple)
    aal1 = couple.actor(couple.alice, aal="aal1").claims

    with pytest.raises(Exception, match="row-level security"):
        await as_authenticated(aal1, RATE, couple.id, couple.pet_of_alice.id)
    assert await as_authenticated(aal1, RERATE, couple.pet_of_alice.id) == 0


async def test_a_couple_never_rates_another_couples_pet(couples: Couples) -> None:
    ours = await couples.create()
    theirs = await couples.create()
    await add_event(couples, theirs)
    claims = ours.actor(ours.alice).claims

    with pytest.raises(Exception, match="row-level security"):
        await as_authenticated(claims, RATE, theirs.id, theirs.pet_of_alice.id)
    assert await as_authenticated(claims, RERATE, theirs.pet_of_alice.id) == 0
