# Codex Workflow Hardening Kit

This directory provides a deterministic, fail-loud execution harness for Codex workflows.

## Files

- `.env.example`: environment variable contract.
- `config.schema.json`: machine-readable input schema.
- `config.yaml`: runnable example configuration.
- `preflight.sh`: environment and repository guard checks.
- `validate_inputs.py`: strict input validator.
- `run_workflow.sh`: deterministic orchestrator.
- `smoke_test.sh`: fast multi-case sanity tests.
- `repro_steps.txt`: exact commands and expected outcomes.

## Quick start

```bash
cp codex_workflow/.env.example codex_workflow/.env
python3 codex_workflow/validate_inputs.py --config codex_workflow/config.yaml --schema codex_workflow/config.schema.json
./codex_workflow/run_workflow.sh codex_workflow/config.yaml
```

## Output artifacts

- `codex_workflow/out/run.log`: command trace.
- `codex_workflow/out/status.json`: final run status.
- `codex_workflow/out/smoke/results.json`: smoke-test summary.

## Fail-loud behavior

- Missing or malformed inputs exit non-zero with `[ERROR] VALIDATION_FAILED`.
- Dirty repository blocks execution when `require_clean_git=true`.
- Missing dependencies fail immediately.
- Smoke tests fail the run on any unexpected outcome.
