# CostClaw KPIs

## Primary KPIs

- Review turnaround time for cost or PR audits
- Percentage of recommendations with explicit assumptions
- Percentage of outputs with explicit UNKNOWN items when data is incomplete
- Avoided recurring spend or waste identified through audits
- Validation coverage for each recommended change

## Quality Gates

A CostClaw output is complete only if it includes:

- A deterministic recommendation
- A bounded risk statement
- Repro steps or verification commands
- Named files or systems involved
- Explicit owner and next action

## Anti-KPIs

Treat the following as failures:

- Hand-wavy savings claims
- Unlabeled HHV or LHV energy math
- Hidden assumptions
- Browser-first workflows when direct interfaces exist
- Large diffs without a scoped reason
