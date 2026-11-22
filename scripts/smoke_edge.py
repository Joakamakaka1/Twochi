"""`just smoke-edge`: the post-deploy smoke test through the edge, resolving over DoH.

A local DNS may answer for the domain with something else (this PC's does), so the
address comes from dns.google over HTTPS and every request goes to that address with
the domain as SNI and Host, as `curl --resolve` does. Three GETs cross CloudFront,
without credentials: the API's health, a front route and an API route that does not
exist, which must get the API's own problem+json and never the PWA.

It prints a Markdown table, the evidence a PR carries, and exits 1 when any answer is
not the expected one. The WAF lets in only the allowed countries, so it runs from a PC
in one of them, not from CI: the deploy job invokes the Lambda instead.
"""

import http.client
import ipaddress
import json
import socket
import ssl
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlencode

DOMAIN = "twochi.jcvstro.dev"
DOH_HOST = "dns.google"
TIMEOUT_SECONDS = 15
# DNS constants: the A record type, and the response codes of RFC 1035.
A_RECORD = 1
NOERROR, NXDOMAIN = 0, 3

NETWORK_ERRORS = (OSError, http.client.HTTPException)


class DohError(Exception):
    """dns.google answered something that is not a usable DNS answer."""


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    content_type: str
    body: bytes

    @property
    def media_type(self) -> str:
        """The content type without its parameters, such as the charset."""
        return self.content_type.split(";")[0].strip().lower()

    def is_a(self, status: int, media_type: str) -> bool:
        return self.status == status and self.media_type == media_type


# The domain to resolve; its IPv4 addresses.
type Resolve = Callable[[str], Sequence[str]]
# The domain, the address to connect to and the path; what the edge answered.
type Fetch = Callable[[str, str, str], Response]


@dataclass(frozen=True, slots=True)
class Check:
    path: str
    expected: str
    passes: Callable[[Response], bool]


def _is_json(body: bytes) -> bool:
    try:
        json.loads(body)
    except ValueError:
        return False
    return True


CHECKS = (
    Check(
        "/api/health",
        "200 application/json, a JSON body",
        lambda response: (
            response.is_a(200, "application/json") and _is_json(response.body)
        ),
    ),
    # The front: index.html, or what S3 answers through OAC for a key that is not
    # there, which is all an empty bucket has. CloudFront's own 403s are HTML.
    Check(
        "/",
        "200 text/html, or S3's 403 application/xml while the web bucket is empty",
        lambda response: (
            response.is_a(200, "text/html") or response.is_a(403, "application/xml")
        ),
    ),
    Check(
        "/api/no-existe",
        "404 application/problem+json",
        lambda response: response.is_a(404, "application/problem+json"),
    ),
)

HEADER = ("Route", "Expected", "Got", "Result")


def addresses(answer: bytes) -> list[str]:
    """The IPv4 addresses in a dns.google JSON answer; none when the name is unknown."""
    try:
        data: object = json.loads(answer)
    except ValueError as error:
        raise DohError("dns.google did not answer JSON") from error
    if not isinstance(data, dict):
        raise DohError("dns.google did not answer a JSON object")
    fields = cast("dict[str, object]", data)
    status = fields.get("Status")
    if status == NXDOMAIN:
        return []
    if status != NOERROR:
        raise DohError(f"dns.google answered DNS status {status!r}")
    records = fields.get("Answer", [])
    if not isinstance(records, list):
        raise DohError("dns.google answered records that are not a list")
    found: list[str] = []
    for record in cast("list[object]", records):
        if not isinstance(record, dict):
            raise DohError("dns.google answered a record that is not an object")
        entry = cast("dict[str, object]", record)
        # A CNAME on the way to the addresses is part of the answer too.
        if entry.get("type") != A_RECORD:
            continue
        value = entry.get("data")
        # The address is where the requests connect to: nothing but an IPv4 literal.
        try:
            if not isinstance(value, str):
                raise ValueError(value)
            found.append(str(ipaddress.IPv4Address(value)))
        except ValueError as error:
            raise DohError("dns.google answered an A record without IPv4") from error
    return found


def doh_resolve(domain: str) -> list[str]:
    """Ask dns.google's JSON API for the A records, over HTTPS."""
    connection = http.client.HTTPSConnection(DOH_HOST, timeout=TIMEOUT_SECONDS)
    try:
        query = urlencode({"name": domain, "type": "A"})
        connection.request("GET", f"/resolve?{query}")
        reply = connection.getresponse()
        body = reply.read()
    finally:
        connection.close()
    if reply.status != 200:
        raise DohError(f"dns.google answered HTTP {reply.status}")
    return addresses(body)


def edge_fetch(domain: str, address: str, path: str) -> Response:
    """GET the path at `address`, with `domain` as SNI, certificate name and Host."""
    context = ssl.create_default_context()
    connection = http.client.HTTPSConnection(domain, timeout=TIMEOUT_SECONDS)
    try:
        # A connection that already has a socket never resolves its host.
        connection.sock = context.wrap_socket(
            socket.create_connection((address, 443), timeout=TIMEOUT_SECONDS),
            server_hostname=domain,
        )
        connection.request("GET", path, headers={"User-Agent": "twochi-smoke-edge"})
        reply = connection.getresponse()
        return Response(
            reply.status, reply.headers.get("content-type", ""), reply.read()
        )
    finally:
        connection.close()


def _describe(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"


def _row(check: Check, domain: str, address: str, fetch: Fetch) -> tuple[str, ...]:
    try:
        response = fetch(domain, address, check.path)
    except NETWORK_ERRORS as error:
        return (f"`{check.path}`", check.expected, _describe(error), "FAIL")
    got = f"{response.status} {response.media_type or '(no content type)'}"
    result = "ok" if check.passes(response) else "FAIL"
    return (f"`{check.path}`", check.expected, got, result)


def _table(rows: Sequence[tuple[str, ...]]) -> str:
    """A Markdown table, padded so that it also reads in a terminal."""
    widths = [max(len(row[i]) for row in (HEADER, *rows)) for i in range(len(HEADER))]

    def line(cells: Sequence[str]) -> str:
        padded = (cell.ljust(width) for cell, width in zip(cells, widths, strict=True))
        return "| " + " | ".join(padded) + " |"

    rule = line(["-" * width for width in widths])
    return "\n".join([line(HEADER), rule, *map(line, rows)])


def main(*, resolve: Resolve = doh_resolve, fetch: Fetch = edge_fetch) -> int:
    try:
        found = resolve(DOMAIN)
    except (*NETWORK_ERRORS, DohError) as error:
        sys.stderr.write(f"{DOH_HOST} could not resolve {DOMAIN}: {_describe(error)}\n")
        return 1
    if not found:
        sys.stderr.write(f"{DOH_HOST} has no A record for {DOMAIN}.\n")
        return 1
    address = found[0]
    rows = [_row(check, DOMAIN, address, fetch) for check in CHECKS]
    sys.stdout.write(
        f"`{DOMAIN}` at {address}, resolved over DoH ({DOH_HOST}).\n\n{_table(rows)}\n"
    )
    return 1 if any(row[-1] == "FAIL" for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
