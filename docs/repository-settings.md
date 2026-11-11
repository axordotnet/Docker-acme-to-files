# Repository settings requiring owner access

These are GitHub settings, not settings activated by committing a file.

## Release tags

In Settings → Rules → Rulesets, import `.github/rulesets/release-tags.json`, or create an
active tag ruleset targeting `v*`, with no bypass actors and these rules:

- Restrict updates.
- Restrict deletions.

Do **not** restrict tag creation: the release workflow needs to create new `vX.Y.Z` tags.
This protects Git tags, not GHCR image tags. Versioned images are not rebuilt by the daily job;
`latest` and `sha-<commit>` are rolling tags. Candidate tags `build-<run>-<attempt>` identify builds.

## Security features

In Settings → Code security (labels may vary), verify or enable:

- Dependency graph and Dependabot alerts.
- Dependabot security updates.
- Secret scanning and push protection.
- Private vulnerability reporting.

Keep GitHub notifications for failed Actions and Dependabot alerts enabled. The connected
coding integration may lack administration access; absence of settings in an API response
does not prove that a feature is disabled.

## Optional discoverability

Suggested repository topics: `docker`, `traefik`, `acme`, `letsencrypt`, `certificates`, `pkcs12`.
