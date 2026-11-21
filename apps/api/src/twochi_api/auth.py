"""Verify the Supabase JWT locally with its public keys: signature, issuer, audience,
expiry and the second factor (aal2). The user id always comes from here.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import jwt

from twochi_domain.errors import TwochiError

# The JWT travels in its own header: CloudFront signs the origin request in
# Authorization with SigV4 (AWS, «Borde», option 1).
AUTH_HEADER = "X-Twochi-Auth"

# Supabase signs with asymmetric keys; HS256 is never accepted.
ALGORITHMS = ["ES256", "RS256"]

# Supabase's clock may run slightly ahead of Lambda's: a fresh token is not rejected.
CLOCK_SKEW = timedelta(seconds=5)

_log = logging.getLogger(__name__)

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
        except (jwt.PyJWKClientConnectionError, jwt.PyJWKSetError, ValueError) as error:
            # The key set is unreachable, empty or not JSON: our problem, not theirs.
            _log.error("JWKS unavailable: %s", type(error).__name__)
            raise AuthUnavailableError from error
        except jwt.PyJWTError as error:
            raise _rejected(error) from error
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
                leeway=CLOCK_SKEW,
            )
            user_id = UUID(str(claims["sub"]))
        except (jwt.PyJWTError, ValueError) as error:
            raise _rejected(error) from error
        if claims.get("aal") != "aal2":
            _log.warning("auth rejected: second factor missing")
            raise MfaRequiredError
        return Principal(user_id=user_id)


def _rejected(error: Exception) -> UnauthenticatedError:
    # Only the failure class is logged: never the token or its claims.
    _log.warning("auth rejected: %s", type(error).__name__)
    return UnauthenticatedError()


def _strip_bearer(value: str) -> str:
    scheme, _, rest = value.strip().partition(" ")
    return rest.strip() if scheme.lower() == "bearer" else value.strip()
