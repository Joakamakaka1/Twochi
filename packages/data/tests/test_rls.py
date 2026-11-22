"""RLS and roles straight in SQL, as the browser's token would reach them."""

import json
from collections.abc import Mapping
from uuid import UUID

import pytest
from conftest import ADMIN_URL, API_URL, Couples, TestCouple

from twochi_data.sql import Connection, bool_at, connect, text_at

pytestmark = pytest.mark.anyio

TABLES = ["couples", "profiles", "pets", "pet_needs", "pet_events"]

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
    await couples.admin.execute(
        "insert into app.pet_events "
        "(couple_id, pet_id, source, action, rules_version, idempotency_key) "
        "values ($1, $2, 'system', 'birth', 'test', $3)",
        couple.id,
        couple.pet_of_alice.id,
        f"birth:{couple.pet_of_alice.id}",
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
