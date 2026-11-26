"""The mounted API with a fixed signing key: auth at the edge, the error shape and
the responses, with local Supabase behind the routes that read the game."""

import json
import uuid
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from conftest import API_URL, Couples, TestCouple
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm

from twochi_api.app import create_app
from twochi_api.auth import TokenVerifier
from twochi_application.testing import FixedClock
from twochi_data.database import PostgresDatabase
from twochi_domain.needs import Need

ISSUER = "https://example-project.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KID = "test-key"
USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")

SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())


def public_jwk() -> jwt.PyJWK:
    jwk = json.loads(ECAlgorithm.to_jwk(SIGNING_KEY.public_key()))
    jwk.update(kid=KID, alg="ES256", use="sig")
    return jwt.PyJWK(jwk)


def token(
    *,
    key: ec.EllipticCurvePrivateKey = SIGNING_KEY,
    expires_in: timedelta = timedelta(minutes=5),
    drop: tuple[str, ...] = (),
    **overrides: Any,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(USER_ID),
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + expires_in,
        "aal": "aal2",
        "role": "authenticated",
    }
    claims.update(overrides)
    for claim in drop:
        del claims[claim]
    return jwt.encode(claims, key, algorithm="ES256", headers={"kid": KID})


NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def app_with(
    lookup: Callable[[str], jwt.PyJWK], *, database_url: str | None = API_URL
) -> TestClient:
    verifier = TokenVerifier(issuer=ISSUER, audience=AUDIENCE, signing_key=lookup)
    app = create_app(
        verifier,
        db=PostgresDatabase(database_url, require_tls=False),
        clock=FixedClock(NOW),
    )
    # Unexpected errors must still answer with a problem, so they are not re-raised.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client() -> TestClient:
    return app_with(lambda _token: public_jwk())


def ping(client: TestClient, auth: str | None) -> Any:
    headers = {} if auth is None else {"X-Twochi-Auth": auth}
    return client.post("/api/pings", json={"nonce": "n-1"}, headers=headers)


def test_health_needs_no_token(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ping_returns_the_user_from_the_token_and_the_nonce(client: TestClient) -> None:
    response = ping(client, token())
    assert response.status_code == 200
    assert response.json() == {"user_id": str(USER_ID), "nonce": "n-1"}


def test_bearer_prefix_is_accepted(client: TestClient) -> None:
    assert ping(client, f"Bearer {token()}").status_code == 200


@pytest.mark.parametrize(
    "auth",
    [
        None,
        "",
        "not-a-jwt",
        token(key=OTHER_KEY),
        token(expires_in=timedelta(minutes=-1)),
        token(iss="https://someone-else.supabase.co/auth/v1"),
        token(aud="anon"),
        token(sub="not-a-uuid"),
        token(drop=("exp",)),
        token(drop=("iat",)),
        token(drop=("sub",)),
        jwt.encode({"sub": str(USER_ID)}, "a-shared-secret-of-32-bytes-long!", "HS256"),
    ],
    ids=[
        "missing",
        "empty",
        "garbage",
        "bad-signature",
        "expired",
        "wrong-issuer",
        "wrong-audience",
        "bad-subject",
        "no-exp",
        "no-iat",
        "no-sub",
        "hs256",
    ],
)
def test_rejects_unauthenticated_requests(client: TestClient, auth: str | None) -> None:
    response = ping(client, auth)
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "unauthenticated"


def test_authorization_header_is_not_read(client: TestClient) -> None:
    # CloudFront signs the origin request in Authorization; the JWT travels apart.
    response = client.post(
        "/api/pings",
        json={"nonce": "n-1"},
        headers={"Authorization": f"Bearer {token()}"},
    )
    assert response.status_code == 401


def test_rejects_tokens_without_second_factor(client: TestClient) -> None:
    response = ping(client, token(aal="aal1"))
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


def test_invalid_body_is_a_problem(client: TestClient) -> None:
    response = client.post(
        "/api/pings", json={"nonce": ""}, headers={"X-Twochi-Auth": token()}
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "invalid_request"


def test_unknown_route_is_a_problem(client: TestClient) -> None:
    response = client.get("/api/nothing-here")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_rejects_tokens_without_aal_claim(client: TestClient) -> None:
    response = ping(client, token(drop=("aal",)))
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


def test_tolerates_a_token_issued_a_moment_ahead_of_our_clock(
    client: TestClient,
) -> None:
    ahead = datetime.now(UTC) + timedelta(seconds=2)
    assert ping(client, token(iat=ahead)).status_code == 200


def test_unknown_key_id_is_unauthenticated() -> None:
    def lookup(_token: str) -> jwt.PyJWK:
        raise jwt.PyJWKClientError("Unable to find a signing key that matches")

    response = ping(app_with(lookup), token())
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


@pytest.mark.parametrize(
    "failure",
    [
        jwt.PyJWKClientConnectionError("JWKS endpoint unreachable"),
        jwt.PyJWKSetError("The JWKS endpoint did not return any usable keys"),
        json.JSONDecodeError("Expecting value", "<html>", 0),
    ],
    ids=["unreachable", "no-usable-keys", "not-json"],
)
def test_broken_key_set_is_unavailable_not_unauthenticated(
    failure: Exception,
) -> None:
    def lookup(_token: str) -> jwt.PyJWK:
        raise failure

    response = ping(app_with(lookup), token())
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "auth_unavailable"


def test_unexpected_error_is_a_problem_without_details() -> None:
    def lookup(_token: str) -> jwt.PyJWK:
        raise RuntimeError("secret internals")

    response = ping(app_with(lookup), token())
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "internal_error"
    assert "secret internals" not in response.text


# Casa. The client is a context manager: one event loop for the database connection.


@pytest.fixture
def game() -> Iterator[TestClient]:
    with app_with(lambda _token: public_jwk()) as client:
        yield client


def home(client: TestClient, auth: str | None) -> Any:
    headers = {} if auth is None else {"X-Twochi-Auth": auth}
    return client.get("/api/homes/me", headers=headers)


def token_of(couple: TestCouple, user: uuid.UUID, **overrides: Any) -> str:
    return token(sub=str(user), couple_id=str(couple.id), **overrides)


@pytest.mark.anyio
async def test_home_returns_the_pet_the_caller_cares_for(
    couples: Couples, game: TestClient
) -> None:
    couple = await couples.create(updated_at=NOW - timedelta(hours=1))

    response = home(game, token_of(couple, couple.bruno))

    assert response.status_code == 200
    pet = response.json()["pet"]
    assert pet["id"] == str(couple.pet_of_alice.id)
    assert pet["name"] == "Ali"
    assert pet["model_key"] == "placeholder"
    assert pet["asleep"] is False
    assert pet["mood"] == "happy"
    assert set(pet["needs"]) == {"hunger", "energy", "hygiene", "fun", "affection"}
    assert pet["needs"]["hunger"] == {
        "value": 74.0,
        "updated_at": "2026-11-22T12:00:00Z",
        "rate_per_hour": -6.0,
    }


@pytest.mark.anyio
async def test_home_has_no_pet_until_both_people_arrive(
    couples: Couples, game: TestClient
) -> None:
    couple = await couples.create(with_pets=False)

    response = home(game, token_of(couple, couple.bruno))

    assert response.status_code == 200
    assert response.json() == {"pet": None}


def test_home_needs_a_token(game: TestClient) -> None:
    response = home(game, None)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_home_needs_the_second_factor(game: TestClient) -> None:
    response = home(game, token(aal="aal1"))

    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


def test_home_without_a_database_is_a_problem_not_a_crash() -> None:
    unreachable = "postgresql://twochi_api:x@127.0.0.1:1/postgres"
    with app_with(lambda _token: public_jwk(), database_url=unreachable) as client:
        response = home(client, token())

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "database_unavailable"


def test_home_without_a_configured_database_is_unavailable() -> None:
    with app_with(lambda _token: public_jwk(), database_url=None) as client:
        response = home(client, token())

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"


@pytest.mark.anyio
async def test_home_never_shows_another_couples_pet(
    couples: Couples, game: TestClient
) -> None:
    ours = await couples.create()
    theirs = await couples.create()
    # Our caretaker's id with the other couple's claim: RLS hides our pet from it.
    forged_mix = token(sub=str(ours.bruno), couple_id=str(theirs.id))

    response = home(game, forged_mix)

    assert response.status_code == 200
    assert response.json() == {"pet": None}


def collections_of(paths: Iterable[str]) -> set[str]:
    """The first segment after /api of each path: the collection it names."""
    return {path.split("/")[2] for path in paths if path.startswith("/api/")}


def test_every_api_collection_is_a_plural_noun() -> None:
    # CODING_STANDARDS, «Nombres»: routes under /api use plural nouns. A caller's own
    # view is `/api/<collection>/me`; health predates the rule.
    singular_allowed = {"health"}
    verifier = TokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, signing_key=lambda _token: public_jwk()
    )
    app = create_app(verifier, db=PostgresDatabase(None), clock=FixedClock(NOW))
    paths: dict[str, object] = app.openapi()["paths"]

    collections = collections_of(paths)
    singular = {c for c in collections if not c.endswith("s")} - singular_allowed

    assert {"homes", "pets", "tastes"} <= collections
    assert singular == set()


def test_the_plural_rule_catches_a_singular_collection() -> None:
    collections = collections_of(["/api/homes/me", "/api/home"])

    assert {c for c in collections if not c.endswith("s")} == {"home"}


# Care actions.


def care(client: TestClient, auth: str | None, pet_id: object, body: object) -> Any:
    headers = {} if auth is None else {"X-Twochi-Auth": auth}
    return client.post(f"/api/pets/{pet_id}/care-actions", json=body, headers=headers)


def feed(key: str = "tap-1", item: str = "pizza") -> dict[str, str]:
    return {"action": "feed", "idempotency_key": key, "item_key": item}


@pytest.mark.anyio
async def test_care_action_applies_and_returns_the_pet(
    couples: Couples, game: TestClient
) -> None:
    couple = await couples.create(needs_of_alices_pet={Need.HUNGER: 50}, updated_at=NOW)

    response = care(
        game, token_of(couple, couple.bruno), couple.pet_of_alice.id, feed()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["rejection"] is None
    assert body["deltas"] == {"hunger": 30.0}
    assert body["reaction"] == {"item_key": "pizza", "affinity": 0}
    assert body["sickness"] is None
    assert body["pet"]["id"] == str(couple.pet_of_alice.id)
    assert body["pet"]["needs"]["hunger"] == {
        "value": 80.0,
        "updated_at": "2026-11-22T12:00:00Z",
        "rate_per_hour": -6.0,
    }
    assert set(body["pet"]) == {"id", "name", "model_key", "asleep", "mood", "needs"}


@pytest.mark.anyio
async def test_a_refused_care_action_is_a_200_with_its_reason(
    couples: Couples, game: TestClient
) -> None:
    couple = await couples.create(updated_at=NOW)

    # Alice is the person this pet represents: she does not care for it.
    response = care(
        game, token_of(couple, couple.alice), couple.pet_of_alice.id, feed()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is False
    assert body["rejection"] == "not_caretaker"
    assert body["deltas"] == {}
    assert body["reaction"] is None
    assert body["sickness"] is None
    assert body["pet"]["needs"]["hunger"]["value"] == 80.0


@pytest.mark.anyio
async def test_another_couples_pet_is_a_404_problem(
    couples: Couples, game: TestClient
) -> None:
    ours = await couples.create(updated_at=NOW)
    theirs = await couples.create(updated_at=NOW)

    response = care(game, token_of(ours, ours.bruno), theirs.pet_of_alice.id, feed())

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "not_found"


@pytest.mark.parametrize(
    ("pet_id", "body"),
    [
        (USER_ID, {"action": "dance", "idempotency_key": "k"}),
        (USER_ID, {"action": "feed"}),
        (USER_ID, {"action": "feed", "idempotency_key": ""}),
        (USER_ID, {"action": "feed", "idempotency_key": "k" * 65}),
        (USER_ID, {"action": "feed", "idempotency_key": "nul\u0000"}),
        ("not-a-uuid", {"action": "feed", "idempotency_key": "k"}),
    ],
    ids=[
        "unknown-action",
        "no-key",
        "empty-key",
        "long-key",
        "nul-in-key",
        "bad-pet-id",
    ],
)
def test_an_invalid_care_action_is_a_422_problem(
    game: TestClient, pet_id: object, body: object
) -> None:
    response = care(game, token(), pet_id, body)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "invalid_request"


def test_a_care_action_needs_a_token(game: TestClient) -> None:
    response = care(game, None, USER_ID, feed())

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_a_care_action_needs_the_second_factor(game: TestClient) -> None:
    response = care(game, token(aal="aal1"), USER_ID, feed())

    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


@pytest.mark.anyio
async def test_a_key_reused_for_another_action_is_a_422_problem(
    couples: Couples, game: TestClient
) -> None:
    couple = await couples.create(updated_at=NOW)
    auth = token_of(couple, couple.bruno)
    pet = couple.pet_of_alice.id
    care(game, auth, pet, feed("reused"))

    response = care(game, auth, pet, {"action": "bathe", "idempotency_key": "reused"})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "idempotency_key_reused"


@pytest.mark.parametrize(
    "body",
    [
        {"action": "feed", "idempotency_key": "k", "item_key": "caviar"},
        {"action": "feed", "idempotency_key": "k", "item_key": "ball"},
        {"action": "play", "idempotency_key": "k", "item_key": "pizza"},
        {"action": "feed", "idempotency_key": "k"},
        {"action": "play", "idempotency_key": "k", "item_key": None},
        {"action": "bathe", "idempotency_key": "k", "item_key": "pizza"},
        {"action": "feed", "idempotency_key": "k", "item_key": 7},
    ],
    ids=[
        "unknown",
        "an-activity-to-eat",
        "a-food-to-play",
        "feed-without-item",
        "play-without-item",
        "an-item-to-bathe",
        "not-a-key",
    ],
)
def test_an_item_that_does_not_fit_the_action_is_its_own_422_problem(
    game: TestClient, body: object
) -> None:
    response = care(game, token(), USER_ID, body)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "invalid_item"


@pytest.mark.anyio
async def test_a_care_action_says_when_the_pet_fell_sick(
    couples: Couples, game: TestClient
) -> None:
    couple = await couples.create(
        needs_of_alices_pet=dict.fromkeys(Need, 19), updated_at=NOW
    )

    response = care(
        game, token_of(couple, couple.bruno), couple.pet_of_alice.id, feed()
    )

    assert response.status_code == 200
    assert response.json()["sickness"] == "fell_sick"


def test_the_contract_names_every_item_of_the_catalogue() -> None:
    verifier = TokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, signing_key=lambda _token: public_jwk()
    )
    app = create_app(verifier, db=PostgresDatabase(None), clock=FixedClock(NOW))
    schemas: dict[str, Any] = app.openapi()["components"]["schemas"]

    # Foods and activities apart, so the front's trays are typed by their kind.
    assert schemas["FoodKey"]["enum"] == [
        "tortilla",
        "paella",
        "pizza",
        "burger",
        "sushi",
        "pasta",
        "tacos",
        "salad",
        "broccoli",
        "strawberries",
        "ice_cream",
        "chocolate",
    ]
    assert schemas["ActivityKey"]["enum"] == [
        "ball",
        "video_games",
        "dance",
        "reading",
        "drawing",
        "puzzle",
    ]
    item_key = (
        {"$ref": "#/components/schemas/FoodKey"},
        {"$ref": "#/components/schemas/ActivityKey"},
    )
    for where in (schemas["CareActionIn"], schemas["ReactionOut"]):
        refs = [
            kind for kind in where["properties"]["item_key"]["anyOf"] if "$ref" in kind
        ]
        assert tuple(refs) == item_key
    assert schemas["Affinity"]["enum"] == [-2, -1, 0, 1, 2]
    assert schemas["SicknessChange"]["enum"] == ["fell_sick", "healed"]


# Tastes: each person rates the pet that represents them (ADR 0015).


def my_tastes(client: TestClient, auth: str | None) -> Any:
    headers = {} if auth is None else {"X-Twochi-Auth": auth}
    return client.get("/api/tastes/me", headers=headers)


def rate(client: TestClient, auth: str | None, item: object, body: object) -> Any:
    headers = {} if auth is None else {"X-Twochi-Auth": auth}
    return client.put(f"/api/tastes/me/{item}", json=body, headers=headers)


@pytest.mark.anyio
async def test_tastes_list_only_what_the_caller_rated_for_their_own_pet(
    couples: Couples, game: TestClient
) -> None:
    couple = await couples.create()
    alice = token_of(couple, couple.alice)

    rated = rate(game, alice, "pizza", {"affinity": 2})
    rate(game, alice, "ball", {"affinity": -2})
    rate(game, alice, "pizza", {"affinity": 1})

    assert rated.status_code == 200
    assert rated.json() == {"item_key": "pizza", "affinity": 2}
    response = my_tastes(game, alice)
    assert response.status_code == 200
    assert response.json() == {
        "pet_id": str(couple.pet_of_alice.id),
        "tastes": {"pizza": 1, "ball": -2},
    }


@pytest.mark.anyio
async def test_the_caretaker_never_reads_the_tastes_of_the_pet_they_care_for(
    couples: Couples, game: TestClient
) -> None:
    couple = await couples.create()
    rate(game, token_of(couple, couple.alice), "sushi", {"affinity": 2})

    # Bruno cares for Alice's pet: his `me` is his own pet, with nothing rated.
    response = my_tastes(game, token_of(couple, couple.bruno))

    assert response.json() == {"pet_id": str(couple.pet_of_bruno.id), "tastes": {}}


def test_no_route_reads_the_tastes_of_a_pet_by_its_id() -> None:
    verifier = TokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, signing_key=lambda _token: public_jwk()
    )
    app = create_app(verifier, db=PostgresDatabase(None), clock=FixedClock(NOW))
    paths: dict[str, Any] = app.openapi()["paths"]

    # Only the caller's own: no pet id, no other person, in any route about tastes.
    tastes = {path for path in paths if "taste" in path}
    assert tastes == {"/api/tastes/me", "/api/tastes/me/{item_key}"}
    assert set(paths["/api/tastes/me/{item_key}"]) == {"put"}


@pytest.mark.anyio
async def test_tastes_have_no_pet_until_both_people_arrive(
    couples: Couples, game: TestClient
) -> None:
    couple = await couples.create(with_pets=False)
    alice = token_of(couple, couple.alice)

    listed = my_tastes(game, alice)
    rated = rate(game, alice, "pizza", {"affinity": 2})

    assert listed.json() == {"pet_id": None, "tastes": {}}
    assert rated.status_code == 409
    assert rated.headers["content-type"] == "application/problem+json"
    assert rated.json()["code"] == "no_pet_yet"


@pytest.mark.parametrize("item", ["caviar", "PIZZA", "pizza%20", "1"])
def test_rating_an_unknown_item_is_an_invalid_item(game: TestClient, item: str) -> None:
    response = rate(game, token(), item, {"affinity": 1})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "invalid_item"


@pytest.mark.parametrize(
    "body",
    [
        {"affinity": 3},
        {"affinity": -3},
        {"affinity": "2"},
        {"affinity": 1.5},
        {"affinity": True},
        {},
    ],
    ids=["above", "below", "text", "fraction", "boolean", "missing"],
)
def test_an_affinity_out_of_range_is_a_422_problem(
    game: TestClient, body: object
) -> None:
    response = rate(game, token(), "pizza", body)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "invalid_request"


def rate_pizza(client: TestClient, auth: str | None) -> Any:
    return rate(client, auth, "pizza", {"affinity": 1})


TASTE_ROUTES = pytest.mark.parametrize(
    "call", [my_tastes, rate_pizza], ids=["get", "put"]
)


@TASTE_ROUTES
def test_tastes_need_a_token(game: TestClient, call: Callable[..., Any]) -> None:
    response = call(game, None)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


@TASTE_ROUTES
def test_tastes_need_the_second_factor(
    game: TestClient, call: Callable[..., Any]
) -> None:
    response = call(game, token(aal="aal1"))

    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


def test_the_tastes_contract_names_the_catalogue() -> None:
    verifier = TokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, signing_key=lambda _token: public_jwk()
    )
    app = create_app(verifier, db=PostgresDatabase(None), clock=FixedClock(NOW))
    schemas: dict[str, Any] = app.openapi()["components"]["schemas"]

    item_key = [
        {"$ref": "#/components/schemas/FoodKey"},
        {"$ref": "#/components/schemas/ActivityKey"},
    ]
    assert schemas["TasteOut"]["properties"]["item_key"]["anyOf"] == item_key
    assert schemas["TasteIn"]["properties"]["affinity"] == {
        "$ref": "#/components/schemas/Affinity"
    }
    assert schemas["TastesOut"]["required"] == ["pet_id", "tastes"]
    # The map's keys are the catalogue's: as an enum for JSON Schema, and as one
    # optional property per item, which is what the generated client types.
    tastes = schemas["TastesOut"]["properties"]["tastes"]
    assert tastes["propertyNames"] == {"anyOf": item_key}
    catalogue = [*schemas["FoodKey"]["enum"], *schemas["ActivityKey"]["enum"]]
    assert tastes["properties"] == {
        key: {"$ref": "#/components/schemas/Affinity"} for key in catalogue
    }
    assert tastes["additionalProperties"] is False
    assert "required" not in tastes


# Gustos descubiertos: Casa shows the caretaker what they saw, never the tastes.


@pytest.mark.anyio
async def test_home_shows_the_tastes_the_caretaker_discovered(
    couples: Couples, game: TestClient
) -> None:
    couple = await couples.create(updated_at=NOW)
    bruno = token_of(couple, couple.bruno)
    rate(game, token_of(couple, couple.alice), "pizza", {"affinity": 2})
    rate(game, token_of(couple, couple.alice), "ball", {"affinity": -2})
    before = home(game, bruno).json()["pet"]["discovered"]

    care(game, bruno, couple.pet_of_alice.id, feed("tap-1", "pizza"))

    assert before == {}
    # Ball was rated but never given: still undiscovered.
    assert home(game, bruno).json()["pet"]["discovered"] == {"pizza": 2}


def test_the_home_contract_names_the_catalogue_in_the_tastes_discovered() -> None:
    verifier = TokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, signing_key=lambda _token: public_jwk()
    )
    app = create_app(verifier, db=PostgresDatabase(None), clock=FixedClock(NOW))
    schemas: dict[str, Any] = app.openapi()["components"]["schemas"]

    pet = schemas["HomeOut"]["properties"]["pet"]["anyOf"][0]["$ref"].split("/")[-1]
    assert "discovered" in schemas[pet]["required"]
    discovered = schemas[pet]["properties"]["discovered"]
    assert discovered["additionalProperties"] is False
    catalogue = [*schemas["FoodKey"]["enum"], *schemas["ActivityKey"]["enum"]]
    assert discovered["properties"] == {
        key: {"$ref": "#/components/schemas/Affinity"} for key in catalogue
    }
    # The care response's pet is the same as ever: its reaction is what discovers.
    assert "discovered" not in schemas["PetOut"]["properties"]
