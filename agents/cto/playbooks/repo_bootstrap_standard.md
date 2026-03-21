# Repository Bootstrap Standard

Every managed repo must have:

- a registry entry in `agents/cto/repos/registry.yaml`
- a health file in `agents/cto/repos/health/`
- a PR tracker in `agents/cto/repos/pr_tracking/`
- a CI tracker in `agents/cto/repos/ci_tracking/`
- documented lint, test, build, and deploy commands
- branch protection expectations
- explicit maintainership, or `UNKNOWN` if not yet verified

Unknowns are acceptable during bootstrap, but only if they are explicit and paired with a next action.
