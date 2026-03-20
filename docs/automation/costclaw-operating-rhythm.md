---
title: CostClaw operating rhythm
description: Run a deterministic daily, weekly, and monthly cost review loop for tokens, retries, routing, and context usage.
---

## Purpose

Use this operating rhythm when you want OpenClaw cost work to stay measurable, auditable, and hard to game.

The goal is not to produce more reports. The goal is to catch spend regressions early, rank the largest waste sources, and ship small changes with measurable savings.

## Continuous loop

Run this loop for every cost optimization task:

1. Observe
2. Diagnose
3. Prioritize
4. Design
5. Validate
6. Implement
7. Measure
8. Learn
9. Repeat

## Required baseline

Do not claim savings without a baseline.

Every cost review should pin:

- time window
- workload or traffic slice
- token totals
- cost totals
- retry totals
- routing path used
- context size or payload size
- success and failure counts

If any of those fields are missing, mark the result as `UNKNOWN` and do not report realized savings as final.

## Daily review

Run these checks every day:

- review token and cost deltas
- inspect retry spikes
- inspect context bloat
- inspect routing inefficiencies
- inspect top waste opportunities
- review prior changes for regressions

### Daily output

Record:

- baseline window
- current window
- token delta
- cost delta
- retry delta
- routing delta
- context delta
- top 3 waste sources
- regressions found
- next action

## Weekly review

Run these checks every week:

- publish top 10 waste sources
- publish realized savings
- publish failed experiments
- reassess subagent ROI
- review schedule and cron waste
- review cache miss patterns
- review retrieval payload inflation

### Weekly output

Record:

- ranked waste table
- realized savings with before and after windows
- failed experiments and why they failed
- subagent ROI notes
- cache miss drivers
- retrieval payload inflation notes
- changes approved for next week

## Monthly review

Run these checks every month:

- re-rank architecture-level refactors
- retire low-value optimizations
- tighten routing rules
- tighten memory loading rules
- evaluate benchmark and pricing changes

### Monthly output

Record:

- top architecture refactors by expected impact
- optimizations to retire
- routing rule changes to test
- memory loading rule changes to test
- benchmark or pricing assumptions that changed

## Metrics to track

Track the same core metrics across every cadence:

- total tokens
- total cost
- retries
- retry loops
- average and p95 context size
- routing path frequency
- cache misses
- retrieval payload size
- successful tasks
- failed tasks

If you change the metric definitions, update the automation config and the report template in the same pull request.

## Report template

Use this shape for non-trivial CostClaw outputs:

- execution path chosen
- why it was chosen
- why browser automation was rejected
- systems involved
- files or artifacts used
- actions taken
- result
- blockers
- retry or escalation state

## Example local checks

```bash
pnpm check
pnpm test
pnpm openclaw status --usage
pnpm openclaw gateway usage cost
```

Use targeted commands where possible. Avoid expensive full-suite runs when the change is documentation-only or config-only.

## Acceptance criteria

A CostClaw change is done when:

1. the cadence is documented
2. the automation config matches the documented cadence
3. the tracked metrics are explicit
4. the output format is explicit
5. the change can be reviewed without guessing what success means

## Related docs

- [Task routing specification](/automation/task-routing)
- [Usage tracking](/concepts/usage-tracking)
- [Retry behavior](/concepts/retry)
- [Session pruning](/concepts/session-pruning)
