# EldonOpenClaw to OpenClaw consolidation report

## Scope and objective

This document is a forensic consolidation plan for retiring `Eldonlandsupply/EldonOpenClaw` and migrating any durable value into `openclaw/openclaw`.

- **Source repo (to retire):** `Eldonlandsupply/EldonOpenClaw`
- **Destination repo (canonical):** `openclaw/openclaw`
- **Goal:** preserve useful artifacts, avoid duplicate implementations, and deprecate the source repository with an auditable trail.

## Executive summary

1. OpenClaw is a large TypeScript and Node monorepo with broad platform and channel support.
2. EldonOpenClaw is a smaller Python and asyncio Raspberry Pi runtime with deployment automation and Pi-focused documentation.
3. Repository histories are independent, so migration should be selective, not a raw merge.
4. Path names overlap (`.github`, `docs`, `scripts`, `src`, `.env.example`), but implementation details and runtime models differ.

## Forensic constraints

### Confirmed facts

- The current OpenClaw repo layout indicates a large monorepo with mixed runtimes and multiple channel implementations.
- Existing OpenClaw docs already include gateway, install, testing, channels, and platform material.

### Unknowns that must be resolved before final cutover

- Direct tree-level access to the current `EldonOpenClaw` repository snapshot in this environment.
- License compatibility details for all source-only scripts and docs inside `EldonOpenClaw`.
- Whether any production devices currently depend on EldonOpenClaw-only behavior.

## Top-level path audit and disposition

The table below captures the known overlap from the audit brief, plus migration disposition.

| Path                         |                       Exists in OpenClaw | Exists in EldonOpenClaw | Status           | Migration treatment                                                                                 |
| ---------------------------- | ---------------------------------------: | ----------------------: | ---------------- | --------------------------------------------------------------------------------------------------- |
| `.github/`                   |                                      Yes |                     Yes | Different        | Keep OpenClaw CI as source of truth, port only narrowly useful workflow logic after security review |
| `docs/`                      |                                      Yes |                     Yes | Different        | Import Raspberry Pi operational content into OpenClaw docs and normalize style/links                |
| `scripts/`                   |                                      Yes |                     Yes | Different        | Port only scripts that fill an OpenClaw gap and make them idempotent                                |
| `src/`                       |                                      Yes |                     Yes | Different        | Do not merge trees, translate feature intent into OpenClaw architecture                             |
| `.env.example`               |                                      Yes |                     Yes | Different        | Diff variable sets, add only missing and valid knobs to OpenClaw docs/config                        |
| `main.py`                    |                   No (Python entrypoint) |                     Yes | Source only      | Treat as legacy runtime reference, not a direct code import                                         |
| `systemd/` deployment assets |           Partial (service docs/scripts) |                     Yes | Likely different | Extract generic service units and publish under OpenClaw platform docs/scripts                      |
| YAML config layer            | Partial (OpenClaw config system differs) |                     Yes | Different        | Map settings into OpenClaw config keys, avoid dual config systems                                   |

## Migration plan

### Phase 1, evidence collection

1. Export full tree and commit history metadata from EldonOpenClaw.
2. Produce file-level diff inventory against OpenClaw path families (`docs`, `scripts`, `.github`, config samples).
3. Tag each candidate as `PORT`, `ADAPT`, `ARCHIVE`, or `DROP` with owner and rationale.

**Deliverables**

- `artifacts/eldonopenclaw-tree-manifest.json`
- `artifacts/eldonopenclaw-to-openclaw-diff.csv`
- `artifacts/eldonopenclaw-disposition-log.csv`

### Phase 2, selective porting

1. Port Raspberry Pi operational docs into OpenClaw docs with generic placeholders.
2. Re-implement required runtime behavior in existing OpenClaw service patterns, do not embed a parallel Python runtime in core.
3. Convert useful deployment scripts to OpenClaw script conventions and test on clean hosts.

**Acceptance criteria**

- No duplicated control-plane runtime paths for the same function.
- All imported docs use OpenClaw terminology and Mintlify-compatible links.
- New scripts are idempotent and include failure-safe checks.

### Phase 3, compatibility and test gate

1. Add smoke checks for migrated Pi deployment path.
2. Validate no regressions in OpenClaw baseline checks.
3. Document operator runbooks for cutover and rollback.

**Acceptance criteria**

- OpenClaw build and test checks remain green.
- Pi deployment flow is documented and reproducible from a clean environment.
- Rollback path is documented and validated.

### Phase 4, repository deprecation

1. Freeze EldonOpenClaw branch protection to block new feature work.
2. Add archival banner and deprecation notice with migration date.
3. Preserve read-only tags and release artifacts for auditability.
4. Redirect operators to OpenClaw docs and support channels.

**Acceptance criteria**

- Source repo set to read-only archived state.
- Deprecation notice links to OpenClaw canonical locations.
- Audit log includes migration commit map and ownership sign-off.

## Risk register

| Risk                                                         | Impact                                  | Mitigation                                           | Owner            | Due                       |
| ------------------------------------------------------------ | --------------------------------------- | ---------------------------------------------------- | ---------------- | ------------------------- |
| Blind directory merges across overlapping paths              | Breaks monorepo CI and runtime behavior | Enforce file-level disposition before copy           | Repo maintainers | Before first port PR      |
| Importing stale or Pi-specific assumptions into generic docs | Operator misconfiguration               | Rewrite docs using placeholders and tested commands  | Docs owner       | During docs port          |
| Running dual runtimes (Python + TS) for same capability      | Operational drift                       | Re-implement capability inside OpenClaw architecture | Platform owner   | Before production cutover |
| Secret leakage from legacy examples                          | Security exposure                       | Scan and replace with obvious placeholders           | Security owner   | Before merge              |
| Untracked behavior differences during translation            | Hidden regression risk                  | Add focused smoke checks for migrated behavior       | QA owner         | Before deprecation        |
| Incomplete deprecation messaging                             | Fragmented operator usage               | Pin deprecation issue and archive timeline           | Maintainer       | At archive cut            |

## Cutover checklist

- [ ] EldonOpenClaw tree manifest captured and stored.
- [ ] Disposition log complete for all top-level paths.
- [ ] Port PRs merged with test evidence.
- [ ] OpenClaw docs updated with migration notes.
- [ ] EldonOpenClaw archived and marked deprecated.
- [ ] Post-cutover monitoring window completed with no critical regressions.

## Open items

1. `UNKNOWN`: exact file inventory and commit-level attribution of EldonOpenClaw in this environment.
2. `UNKNOWN`: whether any EldonOpenClaw-only production automation must be preserved as-is.
3. `UNKNOWN`: final deprecation date and communications owner.
