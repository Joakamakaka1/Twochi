"""Verify the Supabase JWT locally with its public keys: signature, issuer, audience,
expiry and the second factor (aal2). The user id always comes from here.
"""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import jwt

from twochi_domain.errors import TwochiError

# The JWT travels in its own header: CloudFront signs the origin request in
# Authorization with SigV4 (AWS, «Borde», option 1).
AUTH_HEADER = "X-Twochi-Auth"

# Supabase signs with asymmetric keys; HS256 is never accepted.
ALGORITHMS = ["ES256", "RS256"]

type SigningKeyLookup = Callable[[str], jwt.PyJWK]
"""Return the public key that signed a token, by its `kid`."""


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID


class UnauthenticatedError(TwochiError):
    """The token is missing, malformed, forged, expired or not ours."""


class MfaRequiredError(TwochiError):
    """The token is valid but lacks the second factor."""


class AuthUnavailableError(TwochiError):
    """The public keys could not be fetched."""


class TokenVerifier:
    def __init__(
        self, *, issuer: str, audience: str, signing_key: SigningKeyLookup
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._signing_key = signing_key

    def verify(self, header_value: str | None) -> Principal:
        """Return who sent the request, or raise why they cannot be trusted."""
        token = _strip_bearer(header_value or "")
        if not token:
            raise UnauthenticatedError
        try:
            key = self._signing_key(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWKClientConnectionError as error:
            raise AuthUnavailableError from error
        except jwt.PyJWTError as error:
            raise UnauthenticatedError from error
        try:
            user_id = UUID(str(claims["sub"]))
        except ValueError as error:
            raise UnauthenticatedError from error
        if claims.get("aal") != "aal2":
            raise MfaRequiredError
        return Principal(user_id=user_id)


def _strip_bearer(value: str) -> str:
    scheme, _, rest = value.strip().partition(" ")
    return rest.strip() if scheme.lower() == "bearer" else value.strip()
