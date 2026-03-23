# Merge Intake Report, OpenClaw v2026.3.22-beta.1

## Execution path

- Path: web release review -> local repo inspection -> targeted code adaptation -> local validation.
- Browser Rejection: not used. GitHub release notes and repo inspection were sufficient through web fetch and local source review.

## Repo baseline inspected

- Package version: `2026.2.12`.
- Key areas reviewed: gateway discovery, onboarding, CLI gateway discovery output, media parsing, memory tools, web/media loading, startup paths, and release-note breaking changes.

## Upstream change grouping

### 1. Bug fixes

- Gateway discovery fails closed on unresolved Bonjour and DNS-SD endpoints.
- `memory_search` and `memory_get` registration resilience.
- Telegram reply fallback behavior, polling timeout handling.
- OpenAI-compatible tool-call and Responses compatibility fixes.
- Multiple Android, WhatsApp, Slack, Control UI, and startup regressions.

### 2. Security improvements

- Exec env sandbox tightening.
- Voice webhook pre-auth request hardening.
- Windows local-media UNC and remote `file://` path blocking.
- iOS pairing scope binding.
- Nostr inbound DM policy enforcement.
- Synology Chat recipient binding hardening.
- Plugin marketplace path escape rejection.

### 3. Reliability / uptime improvements

- Bundled channel plugin startup from built `dist/extensions`.
- Primary model prewarm and retry on startup.
- Gateway health monitor controls.
- WhatsApp reconnect fixes.
- Bonjour advertiser crash suppression.

### 4. Agent orchestration improvements

- Media replies standardized on `details.media`.
- Per-agent reasoning defaults.
- `/btw` side-question flow.
- Memory plugin prompt-section ownership.
- Skill prompt budget fallback.

### 5. Performance / cost improvements

- CLI and configure lazy-loading.
- Agent inbound lazy-loading.
- Reduced startup churn for Discord and general gateway boot.
- Cheaper media parsing paths and prompt handling in several spots.

### 6. Developer experience improvements

- New plugin SDK surface and migration.
- `config set` dry-run and batch support.
- Stable memory CLI entrypoint.
- Plugin testing SDK helpers.

### 7. UI / dashboard improvements

- Canvas expansion button.
- Appearance roundness slider.
- Usage view polish.
- Session routing and preferences fixes.

### 8. Breaking changes

- ClawHub-first plugin install resolution.
- Removal of Chrome extension relay browser path.
- Removal of bundled nano-banana skill path.
- Plugin SDK migration from `openclaw/extension-api`.
- Matrix plugin migration.
- Removal of `CLAWDBOT_*` and `MOLTBOT_*` compatibility env names.
- Removal of `.moltbot` state fallback.

### 9. Optional / opinionated changes

- New marketplaces and bundles.
- Provider catalog churn and default model shifts.
- New web-search providers.
- New Matrix, Feishu, Telegram, Android, and MiniMax features.
- UI appearance changes.

## Merge-intake decision table

| Upstream change                                               | Why it matters                                                | Fit for this fork | Risk   | Action | Reason                                                                            |
| ------------------------------------------------------------- | ------------------------------------------------------------- | ----------------- | ------ | ------ | --------------------------------------------------------------------------------- |
| Discovery fail-closed on unresolved Bonjour endpoints         | Stops TXT-only hints from steering routing or SSH targets     | High              | Low    | Adapt  | Good security win, small surface area, no architecture churn                      |
| `splitMediaFromOutput` fast-path before fence parsing         | Cuts pointless work on common text-only replies               | High              | Low    | Port   | Small, behavior-preserving performance improvement                                |
| Windows UNC and remote `file://` media hardening              | Real security value, but touches many media seams             | Medium            | Medium | Defer  | Worth a separate focused PR, too broad for this intake batch                      |
| Memory tool lazy runtime split and richer unavailable results | Better resilience, but large diff in agent-critical tool path | Medium            | Medium | Reject | Too much churn in a core tool without tight need for this fork                    |
| Startup lazy-loading and model prewarm stack                  | Strong upside, but spans many startup and provider paths      | Medium            | Medium | Defer  | Good candidate for a separate startup-focused PR                                  |
| OpenAI-compatible tool-call / Responses fixes                 | Important if affected providers are in use                    | Medium            | Medium | Defer  | Valuable, but touches large run-paths and needs provider-specific regression work |
| Plugin SDK migration and extension API removal                | Required only if following upstream plugin SDK break          | Low               | High   | Reject | Breaking change, not justified for a selective intake                             |
| ClawHub-first install and new marketplaces                    | Opinionated ecosystem direction                               | Low               | Medium | Reject | Changes package resolution semantics, not needed for fork stability               |
| New provider defaults and catalog churn                       | Keeps upstream current, but changes behavior and cost         | Low               | Medium | Reject | Unclear upside for this fork, high surprise potential                             |
| UI appearance and dashboard feature churn                     | Mostly cosmetic                                               | Low               | Low    | Reject | Not worth widening diff for a repo-surgery intake                                 |

## Selected changes to implement

1. Adapt discovery fail-closed behavior so only resolved SRV endpoints produce connection targets and `wsUrl` values.
2. Port the low-risk media parsing fast-path to avoid unnecessary fence scanning on ordinary text-only output.

## Explicit reject list

- Plugin SDK migration and `openclaw/extension-api` removal.
- ClawHub-first package resolution and marketplace expansion.
- Default model churn, provider catalog churn, and feature-heavy provider additions.
- UI roundness and dashboard-only polish changes.
- Large memory-tool refactor in this batch.

## Blockers / escalation state

- No approvals required.
- No credentials required.
- Remaining deferred items should be handled as separate optional PRs if wanted.
