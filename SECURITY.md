# Security policy

## Supported versions

Security fixes target the latest published version and `main`. No support SLA or independent
security audit is claimed. Rebuild with updated base images and dependencies regularly.

## Reporting a vulnerability

Use GitHub's **Report a vulnerability** button in this repository's Security tab when available.
If private reporting is unavailable, open an issue requesting a private contact channel **without
technical exploit details or sensitive data**. Do not attach real acme.json files, private keys,
PFX files, passwords or certificate account records. Use generated test certificates only.

## Threat model and operational boundaries

- Trusted administrators control source, secret, output mounts and container runtime.
- The output directory must not be writable by untrusted users. Symlink race attacks by a
  concurrent malicious writer inside the output mount are outside the supported threat model.
- The source is read only; ACME account private keys are never intentionally exported.
- Generated filenames are validated, normalized and checked for collisions.
- Files use 0600, generated directories 0700, and the default container UID is non-root.
- PFX secrets are read from files or `PFX_PASSWORD` and never logged; exported PEM private keys
  are unencrypted. An explicitly present environment variable overrides the file, including
  invalid/empty values (which fail validation without fallback). Docker operators may inspect
  container environment variables; Vault environment rotations require container recreation.
- Cryptographic parsing uses PyCA cryptography. Supplied chain signatures and validity periods
  are checked, but no trust-store, revocation or network-based validation is performed.
- Invalid snapshots preserve previous data; previous data can expire and must be monitored.
- Publication uses atomic rename of a symlink on a local Linux filesystem. Consumers must
  resolve the generation once when opening related files to avoid a renewal-time read race.
- Python dependencies are audited in CI. SBOM/provenance are build metadata, not a security
  certification. Base-image vulnerabilities require monitoring and timely image rebuilds.
- This tool has no network listener, telemetry, hooks, shell evaluation or Docker API access.

Use the provided Compose hardening. Limit source exposure, encrypt backups, pin deployment
image digests, and reload downstream applications on renewal. File-based Compose secrets
remain ordinary host files and require appropriate host permissions.
