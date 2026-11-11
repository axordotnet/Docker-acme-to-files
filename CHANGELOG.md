# Changelog

## 0.2.0 — 2026-11-11

- Support Vault-injected `PFX_PASSWORD`, with explicit precedence over file secrets.
- Reject invalid/empty environment passwords without falling back; preserve exact UTF-8 values.
- Add a standalone Vault Compose example and document environment secret rotation.
- Extend password and container integration coverage.
- Integrate Dependabot updates for runtime image, test tools and GitHub Actions.
- Automate versioned images and GitHub releases after successful validation.

## 0.1.0 — initial implementation

- Traefik v2/v3 ACME export to PEM and password-protected PFX.
- RSA/ECDSA, multiple resolvers, SANs and wildcard domain support.
- Polling, one-shot execution, password rotation and health reporting.
- Complete-generation publication with restrictive permissions and one previous generation retained.
- Hardened Compose example, Linux AMD64/ARM64 publication, tests and dependency audit.
- English/French documentation and MIT license.
