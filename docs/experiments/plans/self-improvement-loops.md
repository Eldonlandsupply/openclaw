---
summary: "Nightly trace review loop that clusters failures, ships one small fix, and reruns a fixed eval set"
owner: "openclaw"
status: "proposal"
last_updated: "2026-03-20"
title: "Self-Improvement Loops"
---

# Self-Improvement Loops

## Context

OpenClaw already has the pieces for iterative improvement, traces, routing decisions,
skills, and eval-like checks, but the system does not yet enforce a tight feedback loop
that turns real failures into small, measurable fixes.

The proposed pattern is simple:

1. Review the previous day's traces.
2. Cluster failures by root-cause bucket.
3. Patch one small issue.
4. Rerun a fixed eval set.
5. Keep the change only if the eval set improves or stays flat without regressions.

This is the right shape for OpenClaw because the biggest wins will likely come from
steady improvements to routing, tool selection, memory, and policy handling, not from one
large prompt rewrite.

## Why it matters

- Real user traces expose where the system actually loses time, tools, or context.
- Small patches are easier to attribute than broad prompt churn.
- Fixed eval sets keep the loop honest and limit endless tweaking.
- Nightly cadence makes progress automatic instead of ad hoc.

## Priority, difficulty, and expected upside

- **Priority:** High
- **Difficulty:** Medium
- **Upside:** High

## Core proposal

Add a scheduled optimizer skill plus a fixed eval set.

### Nightly optimizer loop

Run a nightly isolated cron job that:

1. Pulls traces from the previous review window.
2. Clusters failures into four buckets:
   - routing
   - tool use
   - memory
   - policy
3. Ranks clusters by frequency and severity.
4. Picks exactly one small change for the next optimization attempt.
5. Produces a structured report with:
   - changed prompt/tool/skill/file candidates
   - expected benefit
   - rollback plan
   - confidence level
6. Runs the fixed eval set before and after the patch.
7. Rejects the patch if regressions exceed the configured threshold.

### Fixed eval set

The eval set should be stable, versioned, and intentionally boring.

Recommended composition:

- 10 to 20 routing cases
- 10 to 20 tool-selection cases
- 10 to 20 memory-retrieval cases
- 10 to 20 policy-boundary cases
- a small holdout set that the optimizer does not tune against directly

Each case should record:

- input
- expected execution path
- expected tool choice or refusal
- pass or fail rubric
- cost and latency budget

## Implementation sketch

### Phase 1, measurement first

- Define a trace export format with labels for routing, tool, memory, and policy failures.
- Create a small baseline eval set checked into the repo.
- Store nightly summaries as artifacts so regressions are easy to inspect.

### Phase 2, optimizer skill

- Add a bundled skill that reads the prior day's traces and emits a single recommended patch.
- Keep write access narrow. The optimizer should suggest one scoped change, not refactor the system.
- Route execution through cron in an isolated session so the loop is reproducible.

### Phase 3, guarded patching

- Apply one small patch to prompts, tool descriptions, routing heuristics, or memory rules.
- Rerun the fixed eval set.
- Record before and after deltas for pass rate, cost, and latency.
- Auto-reject changes that improve one bucket while materially hurting another.

## Acceptance criteria

- A nightly job runs without manual intervention.
- The job emits a structured failure-cluster report.
- Only one scoped patch is proposed or applied per run.
- The same fixed eval set is rerun on every iteration.
- Reports show before and after results, plus explicit rollback status.
- Holdout regressions block promotion.

## Failure modes

- **Endless tweaking without fixed eval sets:** block rollout unless the same baseline and holdout suites run every time.
- **Overfitting to yesterday's traces:** keep a holdout suite and review trendlines weekly, not just nightly wins.
- **Too-large patches:** enforce one change area per run.
- **Noisy clustering:** require explicit bucket labels and confidence scores before acting.
- **Cost creep:** track token and latency deltas as first-class metrics.

## Recommended first cut

Start with the smallest useful loop:

1. Nightly cron job in an isolated session.
2. Read the last 24 hours of traces.
3. Produce a failure-cluster markdown report.
4. Do not auto-apply fixes yet.
5. Run a baseline eval set and attach the results.

That gets the review loop in place before adding automated patching.

## Browser rejection

Browser automation is not needed here because the work is trace analysis, repo changes,
scheduled execution, and eval runs. Those are all better served by direct repo edits,
cron jobs, and tool or API paths.
