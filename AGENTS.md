# Repository Guidelines

Repo: https://github.com/openclaw/openclaw

## Bootstrap rule

- `AGENTS.md` is bootstrap-only. Keep it high-signal, under ~8 KB when possible. Move verbose procedures to referenced docs/runbooks.
- Browser is last resort. Use this execution order: `API > n8n > MCP > repo edit > DB/storage > CLI > provider API > browser`.
- If a task uses browser automation, record why higher-priority paths were unsuitable. Otherwise include a short `Browser Rejection` note.
- For non-trivial task outputs include: execution path, files used, actions taken, result, blockers, retry/escalation state.
- Escalate only for approvals, missing credentials, policy blocks, low confidence, or repeated failure.

## Repo map

- Core source: `src/`
  - CLI: `src/cli`
  - Commands: `src/commands`
  - Infra: `src/infra`
  - Media: `src/media`
  - Web provider: `src/provider-web.ts`
- Tests: colocated `*.test.ts`, `*.e2e.test.ts`
- Docs: `docs/`
- Extensions: `extensions/*`
- Built output: `dist/`
- Installers for `openclaw.ai`: sibling repo `../openclaw.ai`

## Operating rules

- Runtime baseline: Node 22+, keep Bun and Node paths working.
- Prefer Bun for TS execution: `bun <file.ts>`, `bunx <tool>`.
- TypeScript ESM, strict typing, avoid `any`.
- Reuse existing patterns and dependency injection via `createDefaultDeps`.
- Add brief comments only for non-obvious logic.
- Keep files small when practical; extract helpers instead of making “V2” copies.
- Product/docs/UI name: **OpenClaw**. CLI/package/path/config name: `openclaw`.
- Never edit `node_modules`.
- Never update Carbon.
- Dependencies under `pnpm.patchedDependencies` must stay exact-versioned. Do not patch deps without explicit approval.
- Use the shared CLI palette in `src/terminal/palette.ts`; use `src/cli/progress.ts` for CLI progress; keep status output table-safe via `src/terminal/table.ts`.
- Tool schemas: no `Type.Union`, `anyOf`/`oneOf`/`allOf`, or raw `format` property names. Use optional fields and enum helpers instead.

## Commands

- Install: `pnpm install`
- Dev CLI: `pnpm openclaw ...` or `pnpm dev`
- Build/typecheck: `pnpm build`, `pnpm tsgo`
- Lint/format: `pnpm check`, `pnpm format`, `pnpm format:fix`
- Tests: `pnpm test`, `pnpm test:coverage`
- Pre-commit hooks: `prek install`
- Troubleshooting: `openclaw doctor`

## Testing and change scope

- Run the smallest relevant checks for your change. If logic changes, run `pnpm test` or targeted Vitest coverage for touched areas.
- Vitest coverage thresholds are 70% across lines, branches, functions, statements.
- Do not set test workers above 16.
- Pure test-only changes usually do not need changelog entries.
- User-facing changes usually do.
- Before using iOS/Android simulators, check for connected real devices.
- Do not rebuild the macOS app over SSH.

## Commits, PRs, and multi-agent safety

- Create commits with `scripts/committer "<msg>" <file...>`; avoid manual `git add` / `git commit` unless explicitly required.
- Use concise, action-oriented commit messages.
- Scope commits to your changes only unless the user asked for `commit all`.
- Do not switch branches, edit `.worktrees/*`, or use `git stash` unless explicitly requested.
- If the user asks to push, you may `git pull --rebase` first. Never use `--autostash`, force-push, or discard others' work.
- Unrecognized files may belong to other agents. Ignore them unless your task requires them.
- When working on a GitHub issue or PR, print the full URL in the final report.
- Use literal multiline strings for GitHub issue/comment/PR bodies. Do not embed `\n`.
- Full maintainer PR workflow lives in `.agents/skills/PR_WORKFLOW.md`; use it when the task is PR workflow work.

## Docs and localization

- Docs use Mintlify. Internal links in `docs/**/*.md` are root-relative and omit file extensions.
- Avoid em dashes and apostrophes in doc headings.
- Keep docs generic, no personal device names/hostnames/paths.
- README links should be absolute `https://docs.openclaw.ai/...` URLs.
- If you touch docs, consult the `mintlify` skill and end your reply with any docs URLs you referenced.
- Do not edit `docs/zh-CN/**` unless explicitly asked. Normal flow: update English docs, update glossary if needed, run `scripts/docs-i18n` only when required.

## Channels, providers, and app surfaces

- When refactoring shared messaging logic, consider all built-in and extension channels: `src/telegram`, `src/discord`, `src/slack`, `src/signal`, `src/imessage`, `src/web`, `src/channels`, `src/routing`, and `extensions/*`.
- New channels/extensions/apps/docs must also update `.github/labeler.yml` and matching GitHub labels.
- New connection providers must update every relevant UI surface, status/config form, and docs.
- Never send streaming or partial replies to external messaging channels.

## Security and release guardrails

- Never commit real credentials, phone numbers, videos, or live config values. Use obvious placeholders.
- Secrets/state live under `~/.openclaw/`; common files: `credentials/`, `agents/<agentId>/agent/`, `agents/<agentId>/sessions/`.
- Release/version changes require operator intent. Do not change versions or run publish/release steps without explicit permission.
- For releases, read `docs/reference/RELEASING.md` and `docs/platforms/mac/release.md`.
- NPM publish with 1Password, macOS signing/notary flow, VM operations, and other operator procedures are in `docs/runbooks/agent-operations.md`.

## Platform-specific rules

- macOS gateway runs through the menubar app. Restart via the app or `scripts/restart-mac.sh`, not ad-hoc tmux sessions.
- Use `./scripts/clawlog.sh` for macOS OpenClaw logs.
- SwiftUI work should prefer `Observation` (`@Observable`, `@Bindable`) over new `ObservableObject` usage when feasible.
- For manual `openclaw message send` content containing `!`, use a heredoc.
- Session-log investigations: use `~/.openclaw/agents/<agentId>/sessions/*.jsonl`, not the legacy default session file.

## Extended references

Use these instead of growing this file:

- `docs/runbooks/agent-operations.md` for VM ops, Fly/Signal shortcuts, 1Password/npm publish, voice wake, session-log lookup, and other operator procedures.
- `.agents/skills/PR_WORKFLOW.md` for maintainer PR workflow.
- `docs/help/submitting-a-pr.md` and `docs/help/submitting-an-issue.md` for contribution mechanics.
- `docs/testing.md` for live/docker/mobile test coverage details.
- `docs/concepts/agent-workspace.md` and `docs/concepts/context.md` for bootstrap/context limits.
- `docs/runbooks/secrets-and-authorized-numbers.md` for LOLA WhatsApp command authorization and M365 secret operations.

## AGENTS.md maintenance rule

- If you add a new repo-wide rule here, remove or link any older duplicate.
- If you add a new `AGENTS.md` elsewhere in the repo, add a sibling `CLAUDE.md` symlink to it.
