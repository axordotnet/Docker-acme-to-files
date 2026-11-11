"""Offline exporter. The input and output directories are trusted operator-owned mounts."""

import argparse
import base64
import binascii
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs12

LOG = logging.getLogger("acme-to-files")
MAX_INPUT = 32 * 1024 * 1024
STOP = threading.Event()


class ExportError(Exception):
    """A deliberately secret-free operator message."""


def read_limited(path, limit):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ExportError("Input exceeds the configured safety limit")
    return data


def component(value, domain=False):
    if not isinstance(value, str) or not value or len(value) > 253:
        raise ExportError("Invalid resolver or domain name")
    value = value.lower()
    if domain and value.startswith("*."):
        return "wildcard_" + component(value[2:], domain=True)
    pattern = r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?" if domain else r"[a-z0-9][a-z0-9_-]*"
    if not re.fullmatch(pattern, value) or ".." in value:
        raise ExportError("Unsafe resolver or domain name")
    return value


def decode(value):
    if not isinstance(value, str):
        raise ExportError("Certificate or key is not base64 text")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ExportError("Invalid base64 certificate or key") from exc


def parse_snapshot(raw, password, combined=False):
    """Validate every entry before returning any output; never export ACME account keys."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ExportError("Invalid or incomplete ACME JSON") from exc
    if not isinstance(data, dict) or not data:
        raise ExportError("Expected Traefik v2/v3 resolver storage")
    files = {}
    count = 0
    now = datetime.now(UTC)
    for resolver, store in data.items():
        resolver_name = component(resolver)
        if not isinstance(store, dict):
            raise ExportError("Invalid resolver storage")
        entries = store.get("Certificates") or []
        if not isinstance(entries, list):
            raise ExportError("Invalid certificate list")
        for entry in entries:
            count += 1
            if count > 1000 or not isinstance(entry, dict):
                raise ExportError("Invalid or excessive certificate entries")
            domain = entry.get("domain")
            if not isinstance(domain, dict):
                raise ExportError("Missing certificate domain")
            name = component(domain.get("main"), domain=True)
            prefix = f"{resolver_name}/{name}"
            if f"{prefix}/certificate.cert" in files:
                raise ExportError("Duplicate normalized resolver/domain output")
            try:
                certs = x509.load_pem_x509_certificates(decode(entry.get("certificate")))
                key = ser.load_pem_private_key(decode(entry.get("key")), password=None)
                if not certs or not isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
                    raise ExportError("Expected an RSA or EC certificate and private key")
                leaf = certs[0]
                public_format = (ser.Encoding.DER, ser.PublicFormat.SubjectPublicKeyInfo)
                if leaf.public_key().public_bytes(*public_format) != key.public_key().public_bytes(
                    *public_format
                ):
                    raise ExportError("Certificate and private key do not match")
                for cert in certs:
                    if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
                        raise ExportError("A certificate is expired or not yet valid")
                for child, issuer in zip(certs, certs[1:], strict=False):
                    child.verify_directly_issued_by(issuer)
                sans = domain.get("sans") or []
                if not isinstance(sans, list) or not all(isinstance(s, str) for s in sans):
                    raise ExportError("Invalid SAN metadata")
                actual_names = {
                    n.lower() for n in leaf.extensions.get_extension_for_class(
                        x509.SubjectAlternativeName
                    ).value.get_values_for_type(x509.DNSName)
                }
                expected_names = {domain["main"].lower(), *(s.lower() for s in sans)}
                if not expected_names <= actual_names:
                    raise ExportError("Domain metadata does not match certificate SANs")
                pem = [cert.public_bytes(ser.Encoding.PEM) for cert in certs]
                private = key.private_bytes(
                    ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption()
                )
                files[f"{prefix}/certificate.cert"] = pem[0]
                files[f"{prefix}/private.key"] = private
                files[f"{prefix}/fullchain.pem"] = b"".join(pem)
                files[f"{prefix}/chain.pem"] = b"".join(pem[1:])
                if combined:
                    files[f"{prefix}/combined.pem"] = private + b"".join(pem)
                if password is not None:
                    files[f"{prefix}/bundle.pfx"] = pkcs12.serialize_key_and_certificates(
                        domain["main"].encode(), key, leaf, certs[1:],
                        ser.BestAvailableEncryption(password),
                    )
            except (ValueError, TypeError, UnsupportedAlgorithm, InvalidSignature,
                    x509.ExtensionNotFound) as exc:
                raise ExportError("Invalid certificate, chain, or private key") from exc
    if not files:
        raise ExportError("No certificates found; keeping the previous export")
    return files, count


def write_private(path, content):
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def publish(output, files):
    """Publish a complete generation using one atomic symlink replacement (Linux)."""
    output = Path(output)
    if output.is_symlink():
        raise ExportError("Output root must not be a symlink")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    current = output / "current"
    if os.path.lexists(current) and not current.is_symlink():
        raise ExportError("Output current must be absent or an exporter symlink")
    generation = Path(tempfile.mkdtemp(prefix="generation-", dir=output))
    link = output / (".next-" + generation.name)
    committed = False
    try:
        for relative, content in files.items():
            target = generation / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # parents=True uses default permissions for intermediate directories.
            os.chmod(target.parent.parent, 0o700)
            write_private(target, content)
        link.symlink_to(generation.name, target_is_directory=True)
        os.replace(link, current)
        committed = True
    finally:
        if os.path.lexists(link):
            link.unlink()
        if not committed:
            shutil.rmtree(generation)
    # Keep one previous generation for readers that resolved current before the swap.
    old = sorted(
        (p for p in output.glob("generation-*") if p.is_dir() and not p.is_symlink()
         and p != generation),
        key=lambda p: p.stat().st_mtime_ns, reverse=True,
    )
    for stale in old[1:]:
        shutil.rmtree(stale)


def validate_password(password):
    if not 12 <= len(password) <= 4096 or b"\x00" in password:
        raise ExportError("PFX password must contain 12-4096 bytes and no NUL")
    return password


def password_from_file(path):
    if not path:
        raise ExportError("Set PFX_PASSWORD or PFX_PASSWORD_FILE, or select --no-pfx")
    return validate_password(read_limited(path, 4096).rstrip(b"\r\n"))


def resolve_password(path):
    """An explicitly present environment value takes priority, including empty values."""
    if "PFX_PASSWORD" in os.environ:
        try:
            password = os.environ["PFX_PASSWORD"].encode("utf-8")
        except UnicodeError as exc:
            raise ExportError("PFX_PASSWORD must contain valid UTF-8 text") from exc
        return validate_password(password)
    return password_from_file(path)


def update_health(path, ok, interval):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"ok": ok, "time": time.time(), "interval": interval}))
    os.replace(temp, path)


def healthcheck(path):
    try:
        state = json.loads(read_limited(path, 4096))
        return 0 if state["ok"] and 0 <= time.time() - state["time"] < max(
            90, state["interval"] * 3
        ) else 1
    except (OSError, ValueError, KeyError, TypeError):
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.getenv("ACME_SOURCE", "/input/acme.json"))
    parser.add_argument("--output", default=os.getenv("OUTPUT_DIR", "/output"))
    parser.add_argument("--password-file", default=os.getenv("PFX_PASSWORD_FILE"))
    parser.add_argument("--interval", type=int, default=os.getenv("POLL_INTERVAL", "30"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-pfx", action="store_true")
    parser.add_argument("--combined-pem", action="store_true")
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args(argv)
    health = Path("/tmp/acme-to-files-health.json")  # noqa: S108
    if args.healthcheck:
        return healthcheck(health)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if sys.platform != "linux":
        LOG.error("Run this application in the Linux Docker image")
        return 2
    if args.interval < 1 or args.interval > 86400:
        parser.error("--interval must be between 1 and 86400 seconds")
    output = Path(args.output)
    source = Path(args.source)
    if source.resolve().is_relative_to(output.resolve()):
        parser.error("Source must be outside the output directory")
    if (not args.no_pfx and "PFX_PASSWORD" not in os.environ and args.password_file
            and Path(args.password_file).resolve().is_relative_to(output.resolve())):
        parser.error("Password file must be outside the output directory")
    os.umask(0o077)
    import fcntl

    try:
        if output.is_symlink():
            raise ExportError("Output root must not be a symlink")
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_fd = os.open(output / ".export.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        lock = os.fdopen(lock_fd, "w")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ExportError):
        LOG.error("Cannot lock output; check permissions and ensure only one writer")
        return 2
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: STOP.set())
    previous = None
    with lock:
        while not STOP.is_set():
            success = False
            try:
                raw = read_limited(source, MAX_INPUT)
                password = None if args.no_pfx else resolve_password(args.password_file)
                # Revalidate even unchanged data so expiry is reflected in health.
                files, count = parse_snapshot(raw, password, args.combined_pem)
                digest = hashlib.sha256(raw + b"\x00" + (password or b"")).digest()
                if digest != previous or not (output / "current").is_dir():
                    publish(output, files)
                    previous = digest
                    LOG.info("Exported %d certificate(s)", count)
                success = True
            except ExportError as exc:
                LOG.error("%s", exc)
            except OSError:
                LOG.error("Filesystem failure; check mounts, permissions and free space")
            except Exception:
                # Never include library exception strings: they may contain input secrets.
                LOG.error("Unexpected export failure; previous export retained")
            try:
                update_health(health, success, args.interval)
            except OSError:
                LOG.error("Cannot update health status")
                success = False
            if args.once:
                return 0 if success else 1
            STOP.wait(args.interval)
    return 0
