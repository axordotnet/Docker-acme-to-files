# Contributing

Small focused pull requests are welcome. Discuss breaking output-layout or security changes
in an issue first. Never include real credentials, certificates, keys or account storage.

Use Python 3.13+ on Linux. Install `requirements-dev.txt`, run `ruff check .`, `pytest -v`
and `pip-audit -r requirements.txt`. For container changes also run the container smoke test
described in README.md. Add regression coverage for behavioral/security fixes and update
both English and French documentation when the user-facing contract changes.

Tests must generate disposable keys and certificates. Do not commit fixture private keys.
Keep dependencies minimal and Actions pinned to full commit SHAs. Review Dependabot changes
and run the complete pipeline before merging. PR workflows have read-only repository access
and never publish images; do not introduce `pull_request_target` execution of PR code.

By submitting a contribution, you agree to license it under this repository's MIT license
and confirm you have the right to contribute it. Be respectful and provide actionable feedback.

## Maintainer release checklist

1. Review tests, dependency audit and container smoke test on the intended commit.
2. Update the project version and CHANGELOG.md for the release.
3. Push a `vX.Y.Z` Git tag to trigger versioned AMD64/ARM64 images.
4. Confirm the publication and anonymous pull verification jobs succeeded; if newly created,
   set the GHCR package visibility to Public using the owner account.
5. Inspect the generated SBOM/provenance and publish release notes including the image digest.
6. Configure branch rules requiring the `test` job and enable private vulnerability reporting
   and GitHub secret scanning/push protection where available. These are repository settings;
   committing this document does not enable them.
