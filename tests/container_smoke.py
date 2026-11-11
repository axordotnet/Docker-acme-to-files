"""CI integration: actual image, offline/non-root/read-only, renewals and failure recovery."""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives.serialization import pkcs12
from test_exporter import PASSWORD, make_entry, snapshot

from acme_to_files.app import parse_snapshot


def docker(*args, check=True, env=None):
    return subprocess.run(  # noqa: S603
        ["docker", *args], check=check, capture_output=True, text=True, env=env,
    )  # noqa: S607


def wait_for(predicate, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise AssertionError("Container integration condition timed out")


def main():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source, output = root / "input", root / "output"
        source.mkdir()
        output.mkdir()
        password = root / "password"
        password.write_bytes(PASSWORD)
        raw = snapshot(make_entry())
        (source / "acme.json").write_bytes(raw)
        expected, _ = parse_snapshot(raw, None)
        container = docker(
            "run", "--detach", "--read-only", "--network", "none",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--user", f"{os.getuid()}:{os.getgid()}", "--tmpfs", "/tmp:mode=1777",  # noqa: S108
            "--mount", f"type=bind,src={source},dst=/input,readonly",
            "--mount", f"type=bind,src={output},dst=/output",
            "--mount", f"type=bind,src={password},dst=/password,readonly",
            "acme-to-files:test", "--password-file", "/password", "--interval", "1",
        ).stdout.strip()
        try:
            current = output / "current"
            wait_for(current.is_dir)
            for name, content in expected.items():
                assert (current / name).read_bytes() == content
            first = current.resolve()
            (source / "acme.json").write_text("{")
            wait_for(lambda: docker("exec", container, "python", "-m", "acme_to_files",
                                    "--healthcheck", check=False).returncode == 1)
            assert current.resolve() == first
            replacement = source / "replacement.json"
            replacement.write_bytes(snapshot(make_entry()))
            replacement.replace(source / "acme.json")
            wait_for(lambda: current.resolve() != first)
            wait_for(lambda: docker("exec", container, "python", "-m", "acme_to_files",
                                    "--healthcheck", check=False).returncode == 0)
            second = current.resolve()
            password.write_bytes(b"rotated-test-password")
            wait_for(lambda: current.resolve() != second)
            logs = docker("logs", container).stdout + docker("logs", container).stderr
            assert PASSWORD.decode() not in logs and "PRIVATE KEY" not in logs
            docker("stop", "--time", "5", container)
            state = json.loads(docker("inspect", container).stdout)[0]["State"]
            assert state["ExitCode"] == 0
        finally:
            docker("rm", "--force", container, check=False)
    print("Container export, renewal, recovery, password rotation and SIGTERM passed")
    docker(
        "run", "--rm", "--network", "none", "--entrypoint", "python", "acme-to-files:test",
        "-c", "import importlib.util; "
        "assert importlib.util.find_spec('pip') is None; "
        "assert importlib.util.find_spec('ensurepip') is None",
    )
    environment_smoke()


def environment_smoke():
    """Vault-style environment injection, precedence, recreation and fail-closed behavior."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source, output = root / "input", root / "output"
        source.mkdir()
        output.mkdir()
        (source / "acme.json").write_bytes(snapshot(make_entry()))
        secret = "vault-test-password-é-$value"
        command = [
            "run", "--rm", "--read-only", "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--user", f"{os.getuid()}:{os.getgid()}", "--tmpfs", "/tmp:mode=1777",  # noqa: S108
            "--mount", f"type=bind,src={source},dst=/input,readonly",
            "--mount", f"type=bind,src={output},dst=/output",
            "--env", "PFX_PASSWORD", "acme-to-files:test", "--once",
            "--password-file", "/nonexistent-file",
        ]
        env = {**os.environ, "PFX_PASSWORD": secret}
        result = docker(*command, env=env)
        assert secret not in result.stdout + result.stderr
        current = output / "current"
        pfx = current / "letsencrypt/example.test/bundle.pfx"
        _, cert, _ = pkcs12.load_key_and_certificates(pfx.read_bytes(), secret.encode())
        assert cert is not None
        previous = current.resolve()
        result = docker(*command, env={**env, "PFX_PASSWORD": ""}, check=False)
        assert result.returncode == 1 and current.resolve() == previous
        rotated = "rotated-vault-test-password"
        docker(*command, env={**env, "PFX_PASSWORD": rotated})
        assert current.resolve() != previous
        _, cert, _ = pkcs12.load_key_and_certificates(pfx.read_bytes(), rotated.encode())
        assert cert is not None
        docker(*command, "--no-pfx", env={**env, "PFX_PASSWORD": ""})
        assert not pfx.exists()
    print("Vault environment, exact password, precedence, recreation and --no-pfx passed")


if __name__ == "__main__":
    main()
