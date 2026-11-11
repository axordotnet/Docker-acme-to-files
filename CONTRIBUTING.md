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
2. Update the project version, CHANGELOG.md and `docs/releases/vX.Y.Z.md` for the release.
3. Merge the tested change with the exact merge commit title `release: vX.Y.Z`.
   The pipeline checks for an existing tag before publishing `X.Y.Z`; after image verification
   it creates the Git tag and GitHub release with the release notes and image digest.
   The release token only has repository contents write permission in the final release job.
   Do not reuse a published version. Alternatively, manually push a `vX.Y.Z` Git tag to build
   versioned images (this route does not automatically create release notes).
4. Confirm the publication, anonymous pull verification and release jobs succeeded; if newly created,
   set the GHCR package visibility to Public using the owner account.
5. Inspect the generated SBOM/provenance and the published release notes and image digest.
6. Configure branch rules requiring the `test` job and enable private vulnerability reporting
   and GitHub secret scanning/push protection where available. These are repository settings;
   committing this document does not enable them.
