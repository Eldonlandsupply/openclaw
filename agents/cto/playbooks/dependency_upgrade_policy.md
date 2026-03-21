# Dependency Upgrade Policy

Priority order:

1. Critical security fixes on production-impacting repos.
2. CI-breaking dependency drift.
3. Tooling updates that reduce maintenance burden.
4. Routine ecosystem upgrades with clear payoff.

Rules:

- Keep diffs minimal.
- Do not patch dependencies without explicit approval when the repo policy forbids it.
- Prefer exact versions for patched dependencies.
- Validate lockfile, build, lint, and tests after every upgrade.
- Document remaining follow-up items in the CTO reports.
