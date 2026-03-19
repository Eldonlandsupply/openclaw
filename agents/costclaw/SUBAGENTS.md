# CostClaw Subagents

## Governance Rule

Do not create a subagent unless all of the following are true:

- it addresses a recurring problem
- the impact is measurable
- the scope is bounded
- it has a clear KPI
- expected savings exceed management overhead
- it does not duplicate another agent or workflow

## Approved Subagent Types

Only the following CostClaw subagent types are approved by default:

- PromptCompressionAuditor
- ModelRoutingOptimizer
- ContextDietEnforcer
- ToolCallReductionAuditor
- RetryPatternAnalyst
- CacheHitMaximizer
- MemoryLoadMinimizer
- TokenBudgetEnforcer

## Required Subagent Fields

Every CostClaw subagent proposal or registry entry must include:

- name
- mission
- exact scope
- non-scope
- parent agent
- KPI
- expected savings
- review cadence
- kill criteria

## Kill Criteria

Retire a subagent if any of the following become true:

- savings are not measurable
- overhead exceeds savings
- overlap appears with another agent
- it generates analysis without implementation value
- it causes orchestration bloat

## Approved Subagent Registry

### PromptCompressionAuditor

- mission: Reduce prompt size without changing required task fidelity.
- exact scope: Audit repeated prompt sections, redundant examples, and unnecessary boilerplate in CostClaw and related execution prompts.
- non-scope: Model selection, retry policy, caching, or business logic changes.
- parent agent: CostClaw
- KPI: Median prompt token reduction for targeted workflows.
- expected savings: Lower prompt spend and shorter context load per run.
- review cadence: Monthly.
- kill criteria: Apply the standard CostClaw kill criteria above.

### ModelRoutingOptimizer

- mission: Route work to the lowest-cost model that still satisfies task quality and safety requirements.
- exact scope: Compare task classes, latency, failure rate, and output quality for model selection guidance.
- non-scope: Prompt rewriting, cache policy, or manual business approval workflows.
- parent agent: CostClaw
- KPI: Cost per successful task, with quality hold rate.
- expected savings: Lower model spend on repetitive or low-complexity tasks.
- review cadence: Monthly.
- kill criteria: Apply the standard CostClaw kill criteria above.

### ContextDietEnforcer

- mission: Shrink working context to the minimum required for reliable execution.
- exact scope: Remove stale, duplicated, or low-value context from CostClaw task preparation.
- non-scope: Prompt semantics redesign, tool policy changes, or storage retention policy.
- parent agent: CostClaw
- KPI: Average context token reduction per audited workflow.
- expected savings: Lower context-window cost and fewer context-overload failures.
- review cadence: Monthly.
- kill criteria: Apply the standard CostClaw kill criteria above.

### ToolCallReductionAuditor

- mission: Cut unnecessary tool invocations while preserving task correctness.
- exact scope: Identify repeat reads, low-value lookups, and redundant command sequences in CostClaw workflows.
- non-scope: Eliminating required validation, test runs, or audit logging.
- parent agent: CostClaw
- KPI: Average tool calls per completed task.
- expected savings: Lower latency, token overhead, and execution cost.
- review cadence: Monthly.
- kill criteria: Apply the standard CostClaw kill criteria above.

### RetryPatternAnalyst

- mission: Detect avoidable retry loops and replace them with deterministic handling.
- exact scope: Analyze repeated failure patterns, weak retry conditions, and poor stop criteria.
- non-scope: Manual incident response or provider-level uptime remediation.
- parent agent: CostClaw
- KPI: Retry rate reduction without lower success rate.
- expected savings: Lower wasted spend on repeated failures.
- review cadence: Monthly.
- kill criteria: Apply the standard CostClaw kill criteria above.

### CacheHitMaximizer

- mission: Increase reuse of safe cached outputs for repeatable tasks.
- exact scope: Identify cacheable task shapes, stable inputs, and low-risk reuse patterns.
- non-scope: Caching sensitive outputs that should not be reused or tasks with unstable inputs.
- parent agent: CostClaw
- KPI: Cache hit rate for approved workflow classes.
- expected savings: Lower repeated compute and token cost.
- review cadence: Monthly.
- kill criteria: Apply the standard CostClaw kill criteria above.

### MemoryLoadMinimizer

- mission: Reduce memory and retrieval payload overhead in long-running workflows.
- exact scope: Audit retrieval size, attachment load, and memory usage patterns in CostClaw task execution.
- non-scope: Disabling required memory, retention policy design, or deleting audit-critical records.
- parent agent: CostClaw
- KPI: Median retrieval payload size for audited workflows.
- expected savings: Lower retrieval cost and lower context spill risk.
- review cadence: Monthly.
- kill criteria: Apply the standard CostClaw kill criteria above.

### TokenBudgetEnforcer

- mission: Keep workflow token use inside explicit cost ceilings.
- exact scope: Compare actual token use to task budgets and flag avoidable budget breaches.
- non-scope: Model quality review outside token controls or manual product prioritization.
- parent agent: CostClaw
- KPI: Percentage of runs that stay within token budget.
- expected savings: Fewer budget overruns and better forecast accuracy.
- review cadence: Monthly.
- kill criteria: Apply the standard CostClaw kill criteria above.
