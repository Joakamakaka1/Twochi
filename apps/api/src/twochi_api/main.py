"""ASGI entry point for uvicorn, behind Lambda Web Adapter: `twochi_api.main:app`."""

from twochi_api.wiring import build_app

app = build_app()
