import base64
import copy
import json
import os
import stat
import sys
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from acme_to_files.app import (
    ExportError,
    component,
    healthcheck,
    parse_snapshot,
    password_from_file,
    publish,
    read_limited,
    update_health,
)

PASSWORD = b"test-only-long-password"


def make_entry(kind="ec", domain="example.test", expired=False):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048) if kind == "rsa" else (
        ec.generate_private_key(ec.SECP256R1())
    )
    ca_key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(UTC)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(days=2)).not_valid_after(now + timedelta(days=30))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
            .issuer_name(ca_name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=2))
            .not_valid_after(now + timedelta(days=-1 if expired else 7))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    return {
        "domain": {"main": domain},
        "certificate": base64.b64encode(
            cert.public_bytes(ser.Encoding.PEM) + ca.public_bytes(ser.Encoding.PEM)
        ).decode(),
        "key": base64.b64encode(key.private_bytes(
            ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption()
        )).decode(),
    }


def snapshot(entry):
    return json.dumps({"letsencrypt": {"Account": {"PrivateKey": "NEVER_EXPORT"},
                                      "Certificates": [entry]}}).encode()


@pytest.mark.parametrize("kind", ["ec", "rsa"])
def test_formats_roundtrip(kind):
    files, count = parse_snapshot(snapshot(make_entry(kind)), PASSWORD, combined=True)
    prefix = "letsencrypt/example.test/"
    assert count == 1
    leaf = x509.load_pem_x509_certificate(files[prefix + "certificate.cert"])
    key, cert, cas = pkcs12.load_key_and_certificates(files[prefix + "bundle.pfx"], PASSWORD)
    assert cert == leaf and len(cas) == 1
    assert key.public_key().public_bytes(ser.Encoding.DER, ser.PublicFormat.SubjectPublicKeyInfo) == (
        leaf.public_key().public_bytes(ser.Encoding.DER, ser.PublicFormat.SubjectPublicKeyInfo)
    )
    assert len(x509.load_pem_x509_certificates(files[prefix + "fullchain.pem"])) == 2
    assert len(x509.load_pem_x509_certificates(files[prefix + "chain.pem"])) == 1
    assert files[prefix + "combined.pem"].startswith(b"-----BEGIN PRIVATE KEY-----")
    assert all(b"NEVER_EXPORT" not in value for value in files.values())
    with pytest.raises(ValueError):
        pkcs12.load_key_and_certificates(files[prefix + "bundle.pfx"], b"wrong-password")


def test_no_pfx_and_wildcard():
    files, _ = parse_snapshot(snapshot(make_entry(domain="*.example.test")), None)
    assert "letsencrypt/wildcard_example.test/certificate.cert" in files
    assert not any(p.endswith(".pfx") or p.endswith("combined.pem") for p in files)


@pytest.mark.parametrize("name", ["../../escape", "/tmp/escape", "a\\b", "a\n", "..", ""])  # noqa: S108
def test_unsafe_names(name):
    with pytest.raises(ExportError):
        component(name)


@pytest.mark.parametrize("raw", [b"{", b"[]", b"{}", b'{"le":{"Certificates":[]}}'])
def test_invalid_or_empty_input(raw):
    with pytest.raises(ExportError):
        parse_snapshot(raw, PASSWORD)


def test_key_mismatch():
    entry = make_entry()
    entry["key"] = make_entry()["key"]
    with pytest.raises(ExportError, match="do not match"):
        parse_snapshot(snapshot(entry), PASSWORD)


def test_expired():
    with pytest.raises(ExportError, match="expired"):
        parse_snapshot(snapshot(make_entry(expired=True)), PASSWORD)


def test_san_mismatch():
    entry = make_entry()
    entry["domain"]["main"] = "other.test"
    with pytest.raises(ExportError, match="SAN"):
        parse_snapshot(snapshot(entry), PASSWORD)


def test_invalid_chain():
    entry = make_entry()
    pem = x509.load_pem_x509_certificates(base64.b64decode(entry["certificate"]))
    other = x509.load_pem_x509_certificates(base64.b64decode(make_entry()["certificate"]))
    entry["certificate"] = base64.b64encode(
        pem[0].public_bytes(ser.Encoding.PEM) + other[1].public_bytes(ser.Encoding.PEM)
    ).decode()
    with pytest.raises(ExportError):
        parse_snapshot(snapshot(entry), PASSWORD)


def test_duplicates():
    entry = make_entry()
    raw = json.dumps({"le": {"Certificates": [entry, copy.deepcopy(entry)]}}).encode()
    with pytest.raises(ExportError, match="Duplicate"):
        parse_snapshot(raw, PASSWORD)


def test_multiple_resolvers():
    entry = make_entry()
    raw = json.dumps({"one": {"Certificates": [entry]}, "two": {"Certificates": [entry]}})
    files, count = parse_snapshot(raw, None)
    assert count == 2 and len(files) == 8


def test_password_and_size_limits(tmp_path):
    path = tmp_path / "secret"
    path.write_bytes(PASSWORD + b"\n")
    assert password_from_file(path) == PASSWORD
    with pytest.raises(ExportError):
        read_limited(path, 2)
    path.write_bytes(b"short")
    with pytest.raises(ExportError):
        password_from_file(path)
    with pytest.raises(ExportError):
        password_from_file(None)


def test_health(tmp_path):
    path = tmp_path / "health.json"
    assert healthcheck(path) == 1
    update_health(path, True, 1)
    assert healthcheck(path) == 0
    update_health(path, False, 1)
    assert healthcheck(path) == 1
    path.write_text('{"ok": true, "time": 1, "interval": 1}')
    assert healthcheck(path) == 1


@pytest.mark.skipif(sys.platform != "linux", reason="Linux publication semantics")
def test_atomic_publish_permissions_and_retention(tmp_path):
    out = tmp_path / "out"
    files, _ = parse_snapshot(snapshot(make_entry()), PASSWORD)
    publish(out, files)
    first = (out / "current").resolve()
    for relative, content in files.items():
        path = out / "current" / relative
        assert path.read_bytes() == content
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    publish(out, files)
    assert first.exists()
    publish(out, files)
    assert not first.exists()
    assert len(list(out.glob("generation-*"))) == 2


@pytest.mark.skipif(sys.platform != "linux", reason="Linux publication semantics")
def test_failed_publish_keeps_previous(tmp_path, monkeypatch):
    out = tmp_path / "out"
    files, _ = parse_snapshot(snapshot(make_entry()), None)
    publish(out, files)
    previous = os.readlink(out / "current")

    def fail(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr("acme_to_files.app.os.replace", fail)
    with pytest.raises(OSError):
        publish(out, files)
    assert os.readlink(out / "current") == previous
    assert len(list(out.glob("generation-*"))) == 1


@pytest.mark.skipif(sys.platform != "linux", reason="Linux publication semantics")
def test_reject_output_symlink(tmp_path):
    out = tmp_path / "link"
    out.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ExportError):
        publish(out, {})
