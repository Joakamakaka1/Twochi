"""TLS to Supabase is verify-full: Supabase's root CA only, and the host checked."""

import asyncio
import contextlib
import ipaddress
import ssl
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from cryptography.x509.verification import PolicyBuilder, Store, VerificationError

from twochi_data import sql
from twochi_data.sql import CONNECT_ERRORS, SUPABASE_ROOT_CA, connect

pytestmark = pytest.mark.anyio

# The certificate and intermediate the pooler sent on 2026-11-22: public data, saved so
# the test needs no network. The leaf is valid until 2030-03-11.
POOLER_CHAIN = Path(__file__).parent / "certs" / "pooler-chain.pem"
POOLER_HOST = "aws-0-eu-west-1.pooler.supabase.com"
CHECKED_AT = datetime(2026, 11, 22, tzinfo=UTC)

SSL_REQUEST = (8).to_bytes(4) + (80877103).to_bytes(4)
IMPOSTOR_DSN = "postgresql://twochi_api:never-sent@127.0.0.1:{port}/postgres"


@dataclass(frozen=True, slots=True)
class Issuer:
    certificate: x509.Certificate
    key: ec.EllipticCurvePrivateKey

    def pem(self) -> str:
        return self.certificate.public_bytes(serialization.Encoding.PEM).decode()


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _certificate(
    subject: str,
    key: ec.EllipticCurvePrivateKey,
    issuer: Issuer | None,
    extensions: list[tuple[x509.ExtensionType, bool]],
) -> x509.Certificate:
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(subject))
        .issuer_name(issuer.certificate.subject if issuer else _name(subject))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(hours=1))
        # Python's default context checks in X.509 strict mode, which wants both ids.
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                (issuer.key if issuer else key).public_key()
            ),
            critical=False,
        )
    )
    for extension, critical in extensions:
        builder = builder.add_extension(extension, critical=critical)
    return builder.sign(issuer.key if issuer else key, hashes.SHA256())


def _test_ca() -> Issuer:
    key = ec.generate_private_key(ec.SECP256R1())
    constraints = x509.BasicConstraints(ca=True, path_length=None)
    usage = x509.KeyUsage(
        digital_signature=False,
        content_commitment=False,
        key_encipherment=False,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=True,
        crl_sign=True,
        encipher_only=False,
        decipher_only=False,
    )
    certificate = _certificate(
        "Twochi test CA", key, None, [(constraints, True), (usage, True)]
    )
    return Issuer(certificate, key)


def _server(
    directory: Path, issuer: Issuer | None, names: list[x509.GeneralName]
) -> ssl.SSLContext:
    """A server context for `names`, signed by `issuer` or by itself."""
    key = ec.generate_private_key(ec.SECP256R1())
    certificate = _certificate(
        "impostor", key, issuer, [(x509.SubjectAlternativeName(names), False)]
    )
    cert_path = directory / "server.pem"
    key_path = directory / "server.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert_path, key_path)
    return context


LOOPBACK = x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))
ANOTHER_HOST = x509.DNSName("db.example.com")


@contextlib.asynccontextmanager
async def _impostor(context: ssl.SSLContext) -> AsyncGenerator[int]:
    """A Postgres that offers TLS with `context` and hangs up: a man in the middle."""

    async def answer(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        with contextlib.suppress(
            ssl.SSLError, ConnectionError, asyncio.IncompleteReadError
        ):
            if await reader.readexactly(len(SSL_REQUEST)) == SSL_REQUEST:
                writer.write(b"S")
                await writer.drain()
                await writer.start_tls(context)
                await reader.read(1024)
        writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    try:
        yield server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()


async def test_a_server_supabase_did_not_sign_is_refused(tmp_path: Path) -> None:
    async with _impostor(_server(tmp_path, None, [LOOPBACK])) as port:
        with pytest.raises(ssl.SSLCertVerificationError):
            await connect(IMPOSTOR_DSN.format(port=port), require_tls=True)


async def test_the_dsn_cannot_weaken_the_check(tmp_path: Path) -> None:
    async with _impostor(_server(tmp_path, None, [LOOPBACK])) as port:
        dsn = IMPOSTOR_DSN.format(port=port) + "?sslmode=require"
        with pytest.raises(ssl.SSLCertVerificationError):
            await connect(dsn, require_tls=True)


async def test_a_trusted_certificate_for_another_host_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ca = _test_ca()
    monkeypatch.setattr(sql, "SUPABASE_ROOT_CA", ca.pem())
    async with _impostor(_server(tmp_path, ca, [ANOTHER_HOST])) as port:
        with pytest.raises(ssl.SSLCertVerificationError, match="IP address mismatch"):
            await connect(IMPOSTOR_DSN.format(port=port), require_tls=True)


async def test_a_trusted_certificate_for_the_host_passes_the_handshake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The control for the test above: same CA, right host, so only the host differed.
    ca = _test_ca()
    monkeypatch.setattr(sql, "SUPABASE_ROOT_CA", ca.pem())
    async with _impostor(_server(tmp_path, ca, [LOOPBACK])) as port:
        with pytest.raises(CONNECT_ERRORS) as raised:
            await connect(IMPOSTOR_DSN.format(port=port), require_tls=True)
    assert not isinstance(raised.value, ssl.SSLError)


def _verify_pooler_chain(host: str) -> None:
    leaf, intermediate = x509.load_pem_x509_certificates(POOLER_CHAIN.read_bytes())
    root = x509.load_pem_x509_certificate(SUPABASE_ROOT_CA.encode())
    verifier = (
        PolicyBuilder()
        .store(Store([root]))
        .time(CHECKED_AT)
        .build_server_verifier(x509.DNSName(host))
    )
    verifier.verify(leaf, [intermediate])


def test_the_bundled_root_verifies_the_pooler() -> None:
    _verify_pooler_chain(POOLER_HOST)


def test_the_pooler_certificate_does_not_cover_other_hosts() -> None:
    with pytest.raises(VerificationError):
        _verify_pooler_chain("db.example.com")
