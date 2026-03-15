# EldonOpenClaw Consolidation Record

## Status

- State: Draft consolidation record captured from the audit summary.
- Decision status: Pending maintainer review and execution.
- Last updated: 2026-03-15.

## Scope

This record tracks consolidation planning between Eldon and OpenClaw repositories for:

1. Repository structure and ownership boundaries.
2. Documentation, operational runbooks, and release controls.
3. Integration points, credentials handling, and deployment workflows.
4. Merge sequencing and manual validation checkpoints.

## Validated Findings

The following findings are treated as validated from the supplied audit summary:

1. Consolidation requires a staged merge sequence rather than a single large merge.
2. Documentation and operations artifacts must be aligned before runtime consolidation.
3. Security-sensitive settings and secrets handling require manual confirmation during merge.
4. CI and release checks must be re-verified after each major consolidation step.

## Proposed Merge Procedure

1. **Preparation**
   - Freeze non-essential branch churn where possible.
   - Capture current CI baseline and open-risk inventory.
2. **Documentation and policy alignment**
   - Reconcile canonical docs and operating policies.
   - Confirm naming and ownership conventions.
3. **Incremental code consolidation**
   - Merge by subsystem in small reviewable PRs.
   - Run local and CI checks after each subsystem merge.
4. **Security and release hardening**
   - Validate credentials flow, permissions, and deployment gates.
   - Confirm no broadening of GitHub Actions permissions without need.
5. **Cutover and stabilization**
   - Complete final regression checks.
   - Document residual risks and post-cutover owners.

## Assumptions and Limits

- This document is a consolidation record, not an executable runbook.
- Details are limited to validated points available in the provided audit summary.
- Missing integration details remain `UNKNOWN` until maintainers confirm source systems and credentials.
- This record does not authorize release, publish, or force-history operations.

## Manual Follow-up Checklist

- [ ] Confirm consolidation owners and decision authority.
- [ ] Confirm repo and branch protection expectations.
- [ ] Map each subsystem to a dedicated merge PR.
- [ ] Validate secret scopes and rotation requirements.
- [ ] Verify CI parity commands and required checks.
- [ ] Confirm rollback plan for each consolidation stage.
- [ ] Record unresolved `UNKNOWN` items with owners and dates.
