"""`just smoke-edge`: the DoH answer it reads and the verdict it gives.

Nothing here touches the network: the resolver and the edge are hand-written doubles
that answer what production answered on 2026-11-22, or what it must never answer.
"""

import json
from collections.abc import Mapping

import pytest
from smoke_edge import DOMAIN, DohError, Fetch, Resolve, Response, addresses, main

ADDRESS = "203.0.113.7"

HEALTH = Response(200, "application/json", b'{"status":"ok"}')
PROBLEM = Response(
    404,
    "application/problem+json",
    b'{"type":"about:blank","title":"Not Found","status":404,"code":"not_found"}',
)
# What S3 answers through CloudFront while the web bucket is empty.
EMPTY_BUCKET = Response(
    403, "application/xml", b"<Error><Code>AccessDenied</Code></Error>"
)
INDEX_HTML = Response(200, "text/html", b"<!doctype html><title>Twochi</title>")
# What FastAPI answers on its own, without problems.install.
PLAIN_404 = Response(404, "application/json", b'{"detail":"Not Found"}')

TODAY: Mapping[str, Response] = {
    "/api/health": HEALTH,
    "/": EMPTY_BUCKET,
    "/api/no-existe": PROBLEM,
}


def resolver(*found: str) -> Resolve:
    def resolve(domain: str) -> list[str]:
        assert domain == DOMAIN
        return list(found)

    return resolve


def edge(answers: Mapping[str, Response | Exception]) -> Fetch:
    """An edge that only answers at the address DoH gave, as `curl --resolve` asks."""

    def fetch(domain: str, address: str, path: str) -> Response:
        assert (domain, address) == (DOMAIN, ADDRESS)
        answer = answers[path]
        if isinstance(answer, Exception):
            raise answer
        return answer

    return fetch


def run(answers: Mapping[str, Response | Exception]) -> int:
    return main(resolve=resolver(ADDRESS), fetch=edge(answers))


def row(output: str, path: str) -> str:
    """The table row of one route."""
    (line,) = [line for line in output.splitlines() if line.startswith(f"| `{path}` ")]
    return line


def test_todays_production_answers_pass(capsys: pytest.CaptureFixture[str]) -> None:
    status = run(TODAY)

    output = capsys.readouterr().out
    assert status == 0
    assert ADDRESS in output
    assert "200 application/json" in row(output, "/api/health")
    assert "403 application/xml" in row(output, "/")
    assert "404 application/problem+json" in row(output, "/api/no-existe")
    assert "FAIL" not in output


def test_a_404_that_is_not_problem_json_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = run({**TODAY, "/api/no-existe": PLAIN_404})

    output = capsys.readouterr().out
    assert status == 1
    assert "FAIL" in row(output, "/api/no-existe")
    assert "404 application/json" in row(output, "/api/no-existe")
    # The other routes are still reported: the table is the evidence.
    assert "FAIL" not in row(output, "/api/health")
    assert "FAIL" not in row(output, "/")


def test_the_front_passes_once_index_html_is_deployed() -> None:
    assert run({**TODAY, "/": INDEX_HTML}) == 0


def test_a_content_type_with_parameters_still_matches() -> None:
    html = Response(200, "text/html; charset=utf-8", INDEX_HTML.body)
    problem = Response(404, "Application/Problem+JSON; charset=utf-8", PROBLEM.body)

    assert run({**TODAY, "/": html, "/api/no-existe": problem}) == 0


@pytest.mark.parametrize(
    ("path", "answer"),
    [
        # The PWA answering for the API: the 200 alone proves nothing.
        ("/api/health", INDEX_HTML),
        ("/api/health", Response(200, "application/json", b"not json")),
        ("/api/health", Response(503, "application/problem+json", PROBLEM.body)),
        # CloudFront's own 403 (the WAF's block) is HTML, not S3's XML.
        ("/", Response(403, "text/html", b"<html>Request blocked</html>")),
        (
            "/",
            Response(404, "application/xml", b"<Error><Code>NoSuchKey</Code></Error>"),
        ),
        ("/", Response(200, "application/json", b"{}")),
        # The PWA must never answer for an API route that does not exist.
        ("/api/no-existe", INDEX_HTML),
        ("/api/no-existe", Response(200, "application/problem+json", PROBLEM.body)),
        ("/api/no-existe", EMPTY_BUCKET),
    ],
    ids=[
        "health-html",
        "health-not-json",
        "health-503",
        "front-waf-block",
        "front-404",
        "front-json",
        "missing-route-gets-pwa",
        "missing-route-200",
        "missing-route-s3-403",
    ],
)
def test_any_other_answer_fails(path: str, answer: Response) -> None:
    assert run({**TODAY, path: answer}) == 1


def test_a_route_that_cannot_be_reached_fails_and_the_rest_are_still_checked(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = run({**TODAY, "/api/health": ConnectionResetError("reset by peer")})

    output = capsys.readouterr().out
    assert status == 1
    assert "FAIL" in row(output, "/api/health")
    assert "ConnectionResetError" in row(output, "/api/health")
    assert "FAIL" not in row(output, "/api/no-existe")


def test_without_an_address_nothing_is_called(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = main(resolve=resolver(), fetch=edge({}))

    output = capsys.readouterr()
    assert status == 1
    assert DOMAIN in output.err
    assert "|" not in output.out


@pytest.mark.parametrize(
    "error", [TimeoutError("timed out"), DohError("dns.google answered status 2")]
)
def test_a_resolver_that_fails_is_a_failure_not_a_traceback(
    error: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    def resolve(domain: str) -> list[str]:
        raise error

    status = main(resolve=resolve, fetch=edge({}))

    assert status == 1
    assert "dns.google" in capsys.readouterr().err


# --- The DoH answer (https://dns.google/resolve, JSON) --------------------------------


def doh(**fields: object) -> bytes:
    return json.dumps(
        {"Status": 0, "TC": False, "RD": True, "RA": True, **fields}
    ).encode()


def test_the_a_records_of_a_doh_answer_are_the_addresses() -> None:
    answer = doh(
        Answer=[
            {"name": f"{DOMAIN}.", "type": 1, "TTL": 60, "data": "203.0.113.7"},
            {"name": f"{DOMAIN}.", "type": 1, "TTL": 60, "data": "203.0.113.8"},
        ]
    )

    assert addresses(answer) == ["203.0.113.7", "203.0.113.8"]


def test_other_record_types_are_skipped() -> None:
    # A CNAME on the way to the A records, as a non-alias record would answer.
    answer = doh(
        Answer=[
            {
                "name": f"{DOMAIN}.",
                "type": 5,
                "TTL": 60,
                "data": "d111.cloudfront.net.",
            },
            {"name": "d111.cloudfront.net.", "type": 1, "TTL": 60, "data": ADDRESS},
        ]
    )

    assert addresses(answer) == [ADDRESS]


def test_a_name_that_does_not_exist_has_no_addresses() -> None:
    # NXDOMAIN: status 3 and no Answer at all.
    assert addresses(doh(Status=3, Authority=[{"type": 6}])) == []


@pytest.mark.parametrize(
    "answer",
    [
        b"<html>captive portal</html>",
        b"[]",
        doh(Status=2),
        doh(Answer="203.0.113.7"),
        doh(Answer=[{"type": 1, "data": "not-an-address"}]),
        doh(Answer=[{"type": 1, "data": "2001:db8::7"}]),
    ],
    ids=["not-json", "not-an-object", "servfail", "answer-not-a-list", "junk", "ipv6"],
)
def test_an_answer_that_cannot_be_trusted_is_refused(answer: bytes) -> None:
    with pytest.raises(DohError):
        addresses(answer)
