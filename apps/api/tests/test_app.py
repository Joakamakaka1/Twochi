"""The mounted API with a fixed signing key: auth at the edge, the error shape and
the responses, with local Supabase behind the routes that read the game."""

import json
import uuid
from collections.abc import Callable, Iterator
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
