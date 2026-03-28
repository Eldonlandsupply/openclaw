# Lethe roll-in plan for OpenClaw

## Executive summary

Lethe is a focused memory server that combines a structured event schema, resumable session lifecycle, checkpointing, and compacted context assembly on top of SQLite. The highest-value ideas for OpenClaw are the structured event model (`record`, `log`, `flag`, `task`), explicit session states (`active`, `interrupted`, `completed`), deterministic compaction, and unresolved-flag carry-forward.

What is worth stealing:

- Structured memory events with confidence and task/flag metadata.
- Stable session key mapping and interrupted-session resume behavior.
- Append-only event history plus periodic summary compaction.
- Context assembly that mixes summary plus recent events under hard size caps.
- SQLite-first durability and schema migration discipline.

What is not worth stealing:

- Running a second network service for local memory when OpenClaw already has in-process state and tooling.
- Lethe-specific Go/HTMX dashboard stack, which duplicates OpenClaw UI/TUI surfaces.
- Full server-style API surface for every operation when OpenClaw agents can use local tools directly.

Final recommendation: adapt Lethe patterns into an in-repo, local SQLite "session memory spine" module and expose it through OpenClaw-native tools, not an external sidecar.

## Lethe feature map

| Lethe feature                         | Source file(s)                                             | Value to OpenClaw                            | Risks / mismatch                                          | Decision | Target OpenClaw location                                                              |
| ------------------------------------- | ---------------------------------------------------------- | -------------------------------------------- | --------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------- |
| Event schema (`record/log/flag/task`) | `schema.sql`, `internal/db/migrations/001_init.sql`        | Structured memory that survives restarts     | Duplicate semantics with plain MEMORY.md if not scoped    | Adapt    | `src/memory/session-memory-spine.ts`                                                  |
| Session state machine                 | `internal/session/state.go`, `internal/session/session.go` | Reliable resume and explicit terminal states | Can conflict with existing session store if authoritative | Adapt    | `src/memory/session-memory-spine.ts`                                                  |
| Checkpoint snapshots                  | `schema.sql`, `internal/session/session.go`                | Crash-safe recovery anchor                   | Snapshot payloads can bloat                               | Adapt    | `src/memory/session-memory-spine.ts`                                                  |
| Compaction summary                    | `plugin/src/context-engine.ts`, `internal/api/handlers.go` | Token control and long-run continuity        | Over-aggressive summarization can lose detail             | Adapt    | `src/memory/session-memory-spine.ts`                                                  |
| Summary + recent context assembly     | `plugin/src/context-engine.ts`                             | Keeps prompts short and useful               | Stale summaries if not regenerated                        | Adapt    | `src/memory/session-memory-spine.ts`                                                  |
| Flag review queue                     | `internal/ui/templates/flags`, `internal/db/store.go`      | Non-silent unresolved risk tracking          | Adds process overhead if exposed poorly                   | Adapt    | `src/memory/session-memory-spine.ts`, `src/agents/tools/session-memory-spine-tool.ts` |
| Heartbeat-driven session freshness    | `internal/session/state.go`, `internal/api/handlers.go`    | Better interrupted-state detection           | Heartbeat noise in high-volume channels                   | Adapt    | `src/memory/session-memory-spine.ts`                                                  |
| Standalone Go API + UI server         | `internal/api/*`, `internal/ui/*`                          | Useful for independent deployments           | Adds infra burden and split-brain state inside OpenClaw   | Reject   | N/A                                                                                   |
| Lethe plugin network bridge           | `plugin/src/context-engine.ts`                             | Decoupled integration                        | Extra network hop and auth surface                        | Reject   | N/A                                                                                   |

## OpenClaw current-state assessment

Current OpenClaw memory strengths:

- Mature semantic memory index and search manager for markdown and session transcripts (`src/memory/manager.ts`, `src/memory/search-manager.ts`).
- Existing session transcript and metadata plumbing with validated session paths (`src/config/sessions/paths.ts`).
- Existing `/new` session-memory hook for archival markdown snapshots (`src/hooks/bundled/session-memory/handler.ts`).

Current deficiencies against Lethe-style durability:

- No single structured, append-only session memory table for records/logs/flags/tasks with confidence.
- No first-class unresolved flag lifecycle across restarts.
- No deterministic compacted summary store for long-running session continuity.
- Existing memory retrieval is file-centric, not session-lifecycle-centric.

Strengths to preserve:

- Existing memory search backend and minimal dependency profile.
- Existing session key model and transcript paths.
- Agent tool policy controls and in-process execution model.

## Integration architecture

### Proposed memory model

Use a local SQLite spine with these entities:

- `sessions`: stable session key, lifecycle state, summary, heartbeat timestamps.
- `events`: append-only records/logs/flags/tasks with confidence and optional task/flag metadata.
- `checkpoints`: ordered snapshots per session.
- `compactions`: immutable compaction outputs tied to source event counts.

### Proposed storage path

`~/.openclaw/agents/<agentId>/memory-spine.sqlite` (resolved via OpenClaw state-dir helpers).

### Proposed API, plugin, and skill interfaces

- Internal module API: `SessionMemorySpine` class for CRUD + lifecycle + compaction + context assembly.
- Agent-facing tool: `session_memory_spine` with bounded actions (`start`, `record`, `context`, `compact`, `checkpoint`, `resolve_flag`, `state`, `heartbeat`).
- Keep current memory search tools untouched to preserve backwards compatibility.

### Session lifecycle handling

- `startOrResumeSession`: create if missing, auto-resume if interrupted.
- Explicit transitions with transition validation.
- `heartbeat` updates freshness timestamp without writing noisy events.

### Compaction strategy

- Deterministic trigger path via explicit tool action now.
- Summary generated from event counts + recent task states + unresolved flags.
- Full event history remains in `events`; compaction writes additional summary records, not destructive rewrites.

### Flag lifecycle

- Flags are events with unresolved default.
- `resolve_flag` marks reviewed flags.
- `assembleContext` always carries unresolved flags unless explicitly disabled.

### Checkpoint lifecycle

- Checkpoints are sequence-numbered per session.
- Snapshots remain JSON payloads for flexible resume metadata.

### UI and observability choices

- Phase 1 uses tool outputs and DB inspection.
- No new dashboard service in this phase.
- Future UI integration should plug into OpenClaw status/TUI, not duplicate Lethe UI stack.

## Rejection list

- Lethe Go HTTP server, rejected because OpenClaw should not maintain a second state authority.
- Lethe embedded HTMX dashboard, rejected because OpenClaw already has status surfaces and this adds maintenance burden.
- Network plugin bridge pattern, rejected because local in-process calls are lower latency and lower risk.
- Lethe-specific project/agent registry tables, rejected because OpenClaw already resolves agent scope from session key/config.

## Migration and rollout plan

### Phase 1, minimum useful integration

- Add `SessionMemorySpine` SQLite module.
- Add session lifecycle, event append, flag resolve, checkpoint, compaction, context assembly.
- Add `session_memory_spine` agent tool.
- Add tests for session resume, event persistence, checkpointing, compaction, caps, flag persistence.

### Phase 2, improvements

- Wire automatic lifecycle hooks (start, heartbeat, interrupted/completed transitions) from reply runner.
- Add policy-driven compaction triggers.
- Add context-injection toggle in agent runtime.

### Phase 3, optional dashboard and UX

- Add CLI subcommands for queue-style unresolved flags and task chains.
- Add TUI status card for session spine health and open flags.

## Risk register

| Risk                                  | Impact                                   | Mitigation                                                                          |
| ------------------------------------- | ---------------------------------------- | ----------------------------------------------------------------------------------- |
| Prompt overflow from memory injection | Higher latency and model failure         | Hard char caps and truncation signals in `assembleContext`                          |
| Duplicate memory writes               | Noisy history and confusing recall       | Action-specific writes only, no implicit write on read                              |
| Corrupted session state               | Resume failures                          | SQLite WAL + explicit transition validation                                         |
| Stale summary injection               | Wrong context carry-forward              | Keep recent events separate from summary and recompute compactions                  |
| Agent misuse of tool actions          | Invalid state transitions or junk events | Input validation, bounded enums, strict session key checks                          |
| Migration incompatibility             | Existing flows break                     | New module is additive and optional by default                                      |
| Runtime performance degradation       | Slow tool calls                          | Indexed SQLite schema, capped retrieval windows                                     |
| Security exposure                     | Sensitive memory leakage                 | Local-only storage, no new network listener, existing OpenClaw tool policy controls |
