"""The mounted API with a fixed signing key: auth at the edge and the error shape."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm

from twochi_api.app import create_app
from twochi_api.auth import TokenVerifier

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
    return jwt.encode(claims, key, algorithm="ES256", headers={"kid": KID})


@pytest.fixture
def client() -> TestClient:
    verifier = TokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, signing_key=lambda _token: public_jwk()
    )
    return TestClient(create_app(verifier))


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
