# CostClaw Guardrails

## Purpose

These guardrails define the minimum standard for CostClaw analyses, pull request updates, and change recommendations.

## Guardrails

1. Prefer direct interfaces over browser automation.
2. Use deterministic inputs and name every source file or system used.
3. Mark missing facts as `UNKNOWN`. Do not guess.
4. Keep recommendations minimal, specific, and reviewable.
5. Reject fake cost savings that increase operational, security, or reliability risk.
6. Keep GitHub Actions permissions least privilege.
7. Do not bypass validation to produce a cleaner report.
8. Label every energy calculation as HHV or LHV and flag mixed-basis inputs.
9. End every non-trivial output with a clear owner and next action.

## Required report fields

Every completed CostClaw task must include:

- execution path chosen
- browser rejection note
- files and systems used
- actions taken
- result
- blockers
- retry or escalation state
