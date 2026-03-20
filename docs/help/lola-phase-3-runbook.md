# LOLA Phase 3 runbook

## Execution path

- Path chosen: repo edit.
- Browser rejection: browser automation was not used because all requested Phase 3 changes were direct code and docs edits with local tests.

## Operator checks

1. Enable `LOLA_EXTERNAL_ACTIONS_ENABLED=true` only after validating policy thresholds.
2. Keep `LOLA_EXTERNAL_ACTIONS_DEFAULT_PROVIDER=Outlook` unless another provider wrapper exists.
3. Run `pnpm vitest run src/agents/lola/phase2.test.ts src/agents/lola/phase3.test.ts src/agents/lola/phase1.test.ts`.
4. Review `.lola/phase3-store.json` in dry run before enabling real sends.

## Expected artifacts

- Approval queue entries for internal writes.
- Audit log entries for blocked or executed external actions.
- External action records with provider, summary, and execution status.
