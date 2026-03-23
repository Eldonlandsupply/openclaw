---
title: Upstream watch
description: How the upstream watch automation reviews new upstream releases without auto-merging your fork.
---

# Upstream watch

The upstream watch workflow reviews new releases from `openclaw/openclaw` and proposes only the changes that fit your fork policy. It does not merge anything to `main`.

## What it does

- Runs daily, on manual dispatch, or through `repository_dispatch` with type `upstream-release`.
- Detects the latest upstream release and tag.
- Pulls release notes, the commit range, and changed files.
- Classifies each upstream commit by policy category and fork fit.
- Dry-runs a cherry-pick against the current fork head to detect compatibility.
- Generates a markdown intake report as a workflow artifact.
- Opens or updates separate PRs for safe ports and risky optional ports, only when worthwhile changes exist.
- Fails the workflow when a worthwhile change cannot be classified as compatible.

## Files

- Workflow: `.github/workflows/upstream-watch.yml`
- Rules: `.github/upstream-watch/config.json`
- Report template: `.github/upstream-watch/report-template.md`
- Script entry point: `scripts/upstream-watch.ts`
- Core scoring logic: `src/infra/upstream-watch.ts`

## State and noise control

The workflow stores the last reviewed tag in a single GitHub issue named `Upstream watch state`. That keeps state inside the repository without auto-committing bot metadata.

If the latest upstream release tag matches the stored tag, the workflow writes a report and exits without creating PR noise.

## Fork policy encoded by default

The default rules are conservative.

- Prefer reliability, security, and bug fixes.
- Prefer small patches over broad syncs.
- Reject breaking changes by default.
- Reject churn in fork-specific agent surfaces and extensions.
- Send UI, docs, workflow, and gateway changes through manual-review scoring.
- Reject changes that expand cost or complexity without measurable upside.

## Tune the rules

Edit `.github/upstream-watch/config.json`.

### Common changes

- Add a prefix to `policy.preferPathPrefixes` when a folder is low-risk for your fork.
- Add a prefix to `policy.rejectPathPrefixes` when a folder is fork-owned and should never be auto-ported.
- Adjust `classification.categoryKeywords` if your upstream uses different language in commit subjects.
- Raise or lower the safe patch limits with `maxSafeFiles`, `maxSafeInsertions`, and `maxSafeDeletions`.
- Adjust `fitWeights` and thresholds if the bot is too aggressive or too conservative.

## Manual run

Run the script locally in dry-run mode:

```bash
GITHUB_TOKEN=ghp_example \
GITHUB_REPOSITORY=your-org/openclaw-fork \
node --import tsx scripts/upstream-watch.ts --dry-run
```

Review a specific upstream tag:

```bash
GITHUB_TOKEN=ghp_example \
GITHUB_REPOSITORY=your-org/openclaw-fork \
node --import tsx scripts/upstream-watch.ts --dry-run --release-tag v2026.2.12
```

## Immediate trigger

If you want faster-than-daily reaction time, send a `repository_dispatch` event with type `upstream-release`. The workflow still uses the stored state and will refuse to create duplicate PRs.

## Browser Rejection

Browser automation was not used. GitHub API, local git history, and repository edits were sufficient.
