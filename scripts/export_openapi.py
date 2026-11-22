"""`just openapi`: write the API's OpenAPI document where the front's client reads it.

The document is committed, so the front's job in CI needs no Python: a test keeps the
file in step with the API, and `packages/api-client` checks its generated types
against the file.
"""

import json
import sys
from pathlib import Path
from typing import cast

import jwt

from twochi_api.app import create_app
from twochi_api.auth import TokenVerifier
from twochi_api.wiring import SystemClock
from twochi_data.database import PostgresDatabase

ROOT = Path(__file__).resolve().parent.parent
OPENAPI_FILE = ROOT / "packages" / "api-client" / "openapi.json"


def _no_signing_key(_token: str) -> jwt.PyJWK:
    raise LookupError("The app built to describe itself never verifies a token.")


def openapi_document() -> dict[str, object]:
    """The OpenAPI document of the API, built without settings or a database."""
    app = create_app(
        TokenVerifier(issuer="", audience="", signing_key=_no_signing_key),
        db=PostgresDatabase(None, require_tls=True),
        clock=SystemClock(),
    )
    return cast(dict[str, object], app.openapi())


def main() -> int:
    text = json.dumps(openapi_document(), indent=2, ensure_ascii=False) + "\n"
    # Bytes, so Windows writes the same LF file as CI.
    OPENAPI_FILE.write_bytes(text.encode("utf-8"))
    sys.stdout.write(f"Wrote {OPENAPI_FILE.relative_to(ROOT).as_posix()}.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
