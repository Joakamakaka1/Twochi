"""Composition: the only module that reads configuration. Runs once per Lambda start."""

from fastapi import FastAPI
from jwt import PyJWKClient
from pydantic_settings import BaseSettings, SettingsConfigDict

from twochi_api.app import create_app
from twochi_api.auth import TokenVerifier


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TWOCHI_")

    # Project URL, such as https://<ref>.supabase.co. Not a secret.
    supabase_url: str
    jwt_audience: str = "authenticated"


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
    return create_app(verifier)
