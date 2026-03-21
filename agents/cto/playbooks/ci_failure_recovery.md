# CI Failure Recovery

1. Confirm the failing workflow, branch, commit SHA, and exact failing step.
2. Pull logs through direct integration. If unavailable, mark `MISSING INTEGRATION`.
3. Reproduce locally with the repo's canonical lint, typecheck, build, and test commands.
4. Isolate root cause, avoid speculative fixes.
5. Apply the smallest safe patch.
6. Add or adjust tests when the failure exposes an unguarded regression.
7. Re-run local validation.
8. Push scoped commits, observe remote checks, and update `ci_tracking/<repo>.json`.
9. Record severity, blast radius, root cause, remediation, and prevention follow-up.
