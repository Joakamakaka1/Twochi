"""Composition: the only module that reads configuration. Runs once per Lambda start."""

from datetime import UTC, datetime

from fastapi import FastAPI
from jwt import PyJWKClient
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from twochi_api.app import create_app
from twochi_api.auth import TokenVerifier
from twochi_data.database import PostgresDatabase


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TWOCHI_")

    # Project URL, such as https://<ref>.supabase.co. Not a secret.
    supabase_url: str
    jwt_audience: str = "authenticated"
    # twochi_api through the transaction pooler, for local development. Production
    # must not set it in the Lambda environment, which CI roles read (ADR 0003, 0005):
    # it comes from SSM with TWO-32. Without it, the routes that read the game answer
    # 503 database_unavailable and the rest still work.
    database_url: SecretStr | None = None
    # Only local Postgres, which serves no TLS, turns this off.
    database_require_tls: bool = True


class SystemClock:
    """The `Clock` port on the system clock: the only place that reads it."""

    def now(self) -> datetime:
        return datetime.now(UTC)


def build_app() -> FastAPI:
    """Read the settings and build the app with the JWKS client cached in memory."""
    settings = ApiSettings()  # pyright: ignore[reportCallIssue]
    auth_url = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    # Keys are cached for the life of the process; an unknown kid refetches the set.
    jwks = PyJWKClient(f"{auth_url}/.well-known/jwks.json", lifespan=3600, timeout=2)
    verifier = TokenVerifier(
        issuer=auth_url,
        audience=settings.jwt_audience,
        signing_key=jwks.get_signing_key_from_jwt,
    )
    # The connection opens on first use, so a missing or wrong URL never stops startup.
    # A blank value counts as unset: an empty DSN would make asyncpg try libpq's
    # defaults (localhost:5432) instead of answering unavailable.
    url = settings.database_url
    dsn = (url.get_secret_value() or None) if url is not None else None
    db = PostgresDatabase(dsn, require_tls=settings.database_require_tls)
    return create_app(verifier, db=db, clock=SystemClock())
