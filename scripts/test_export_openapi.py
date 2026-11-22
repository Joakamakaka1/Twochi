"""The OpenAPI document the front's client is generated from stays in step with the API.

The front's types come from `packages/api-client/openapi.json`. This test fails when a
route or a schema changes and the file was not regenerated, so a change in the contract
reaches the front's `tsc` in the same PR.
"""

import json

from export_openapi import OPENAPI_FILE, openapi_document


def test_the_committed_openapi_matches_the_api() -> None:
    committed = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))

    assert committed == openapi_document(), "Stale: run `just openapi` and commit it."


def test_the_document_describes_the_home_route() -> None:
    paths = openapi_document()["paths"]

    assert isinstance(paths, dict)
    assert "/api/homes/me" in paths
