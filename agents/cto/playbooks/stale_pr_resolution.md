# Stale PR Resolution

1. Enumerate open PRs and age.
2. Classify each PR as high-value, low-value, blocked, or abandoned.
3. For high-value PRs, merge base into head, fix conflicts, rerun validation, and tighten the PR description.
4. For blocked PRs, record the single blocker and owner.
5. For abandoned or superseded PRs, recommend closure with rationale.
6. Update `pr_tracking/<repo>.json` with explicit next actions and dates.
