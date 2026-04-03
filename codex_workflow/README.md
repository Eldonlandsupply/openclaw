# Codex Workflow Hardening Kit

## 1. EXECUTIVE DIAGNOSIS

Current weak points:

- Weak input contracts, old config allowed loose keys and partial validation.
- Parser accepted malformed YAML structures silently.
- Execution was non-deterministic, hardcoded steps ignored config retry and timeout values.
- Failure reporting was shallow, status output did not identify failing stage consistently.
- Dependency testing was brittle, based on PATH mutation instead of explicit missing-binary contracts.
- Energy-basis policy existed but had no fail-loud mixed-basis gate.

Likely Codex failures without hardening:

- Unknown schema drift causes command misexecution.
- Hidden assumptions around repo root and cleanliness break CI or local runs.
- Step-level failures are hard to debug due to incomplete run metadata.

## 2. HARDENED PROCESS DESIGN

1. Preflight.
   - Purpose: verify baseline execution safety.
   - Inputs: config path.
   - Action: check config exists, python/bash available, repo root valid git root.
   - Output: `runtime.contract.json` and `[OK] preflight complete`.
   - Failure: `PREFLIGHT_FAILED` with exit codes 10-18.
2. Input validation.
   - Purpose: enforce explicit schema contract.
   - Inputs: config YAML, schema JSON.
   - Action: parse config, validate required keys/types/ranges, enforce HHV/LHV single basis.
   - Output: validation success and runtime contract JSON.
   - Failure: `VALIDATION_FAILED` plus numbered errors.
3. Dependency checks.
   - Purpose: ensure all required binaries exist before execution.
   - Inputs: `dependencies.required_binaries`.
   - Action: `command -v <binary>` per dependency.
   - Output: dependency pass in preflight.
   - Failure: fail on first missing binary.
4. Execution.
   - Purpose: run deterministic enabled steps.
   - Inputs: `execution.steps[*]` with retries/timeouts.
   - Action: run each step in order with bounded retries and timeout.
   - Output: `run.log` with attempt-level records.
   - Failure: `status.json` marks failed stage.
5. Verification.
   - Purpose: assert required artifacts exist.
   - Inputs: `verification.commands`.
   - Action: run each command as a verification step.
   - Output: verification logs.
   - Failure: fail-loud if any command fails.
6. Error handling.
   - Purpose: stop immediately and preserve diagnostics.
   - Inputs: stage failure context.
   - Action: write `status.json` with `result=failed`, stage, message.
   - Output: deterministic failure artifact.
   - Failure: none, this is terminal.
7. Final output.
   - Purpose: emit machine-verifiable terminal status.
   - Inputs: run context.
   - Action: write `status.json` with `result=success`.
   - Output: success/failure state for Codex tooling.
   - Failure: non-zero exit with stage-specific status JSON.

## 3. INPUT SCHEMA

See `config.schema.json`. Key contracts:

- Required sections: `schema_version`, `workflow`, `paths`, `runtime`, `dependencies`, `execution`, `verification`, `error_policy`, `energy`.
- Required scalar constraints:
  - `workflow.name`: `^[a-z0-9_-]{3,64}$`
  - `workflow.run_id`: `^run-[0-9]{8}-[0-9]{4}$`
  - `workflow.mode`: `full|validate_only`
  - `runtime.timeout_seconds`: integer `30..7200`
  - `energy.basis`: `HHV|LHV`
  - `error_policy.fail_fast`: must be `true`
  - `error_policy.allow_silent_fallbacks`: must be `false`
- Required step fields: `id`, `enabled`, `command`, `retry_count`, `timeout_seconds`.

Example source files:

- `config.schema.json`
- `config.yaml`
- `.env.example`

## 4. CODEX EXECUTION CONTRACT

Rules:

- Run from repo root.
- Do not mutate files outside `paths.allow_write_paths` and configured output directories.
- Never run execution steps before `preflight` and `validate_inputs` pass.
- Treat `status.json` as the run-state source of truth.
- Use explicit command artifacts, no hidden session assumptions.

Expected command flow:

1. `python3 codex_workflow/validate_inputs.py --config codex_workflow/config.yaml --schema codex_workflow/config.schema.json`
2. `./codex_workflow/preflight.sh codex_workflow/config.yaml codex_workflow/out/runtime.contract.json`
3. `./codex_workflow/run_workflow.sh codex_workflow/config.yaml`

## 5. VALIDATION LAYER

Fail-loud checks:

- Missing required key, malformed line, invalid run_id, unsupported log level, invalid timeout range.
- Missing `repo_root`, non-git root, dirty git when `require_clean_git=true`.
- Missing binary from dependency list.
- `energy.mixed_basis_input=true` causes hard failure.

Suggested error messages:

- `VALIDATION_FAILED: missing required top-level key: execution`
- `VALIDATION_FAILED: workflow.run_id invalid`
- `PREFLIGHT_FAILED: Missing dependency binary: git`
- `PREFLIGHT_FAILED: Git workspace dirty while runtime.require_clean_git=true`

## 6. FILE AND TOOL MAP

Source-of-truth files:

- `codex_workflow/config.schema.json`
- `codex_workflow/config.yaml`
- `codex_workflow/.env.example`
- `codex_workflow/validate_inputs.py`
- `codex_workflow/preflight.sh`
- `codex_workflow/run_workflow.sh`
- `codex_workflow/smoke_test.sh`
- `codex_workflow/README.md`
- `codex_workflow/repro_steps.txt`

Derived artifacts:

- `codex_workflow/out/runtime.contract.json`
- `codex_workflow/out/run.log`
- `codex_workflow/out/status.json`
- `codex_workflow/out/smoke/*.log`
- `codex_workflow/out/smoke/results.json`

Tool usage contracts:

- `validate_inputs.py`: strict config parse/validate and runtime contract emission.
- `preflight.sh`: repo, dependency, and cleanliness guardrail.
- `run_workflow.sh`: deterministic executor with stage status output.
- `smoke_test.sh`: quick four-case confidence gate.

## 7. TEST PLAN

Minimum tests:

1. Happy path: valid config validates and smoke tests pass.
2. Missing input: remove `run_id`, expect validation failure.
3. Malformed input: invalid run_id format, expect validation failure.
4. Dependency failure: require fake binary, expect preflight failure.

Run:

- `./codex_workflow/smoke_test.sh codex_workflow/config.yaml`

## 8. FINAL IMPROVED VERSION

Use this deterministic master command sequence:

```bash
python3 codex_workflow/validate_inputs.py \
  --config codex_workflow/config.yaml \
  --schema codex_workflow/config.schema.json \
  --emit-runtime codex_workflow/out/runtime.contract.json

./codex_workflow/preflight.sh \
  codex_workflow/config.yaml \
  codex_workflow/out/runtime.contract.json

./codex_workflow/run_workflow.sh codex_workflow/config.yaml
```

Browser Rejection: browser automation was not used, all required operations were completed through repo files and CLI.
