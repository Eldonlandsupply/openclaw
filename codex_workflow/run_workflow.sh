#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-codex_workflow/config.yaml}"
RUNTIME_JSON="codex_workflow/out/runtime.contract.json"
STATUS_JSON="codex_workflow/out/status.json"
RUN_LOG="codex_workflow/out/run.log"

mkdir -p codex_workflow/out codex_workflow/out/logs
: > "$RUN_LOG"

CURRENT_STAGE="init"
CURRENT_MESSAGE="workflow bootstrapping"

write_status() {
  local result="$1"
  local stage="$2"
  local message="$3"
  local exit_code="$4"
  cat > "$STATUS_JSON" <<JSON
{
  "result": "$result",
  "stage": "$stage",
  "message": "$message",
  "exit_code": $exit_code,
  "config_path": "$CONFIG_PATH",
  "runtime_contract": "$RUNTIME_JSON",
  "run_log": "$RUN_LOG"
}
JSON
}

on_exit() {
  local code="$1"
  if [[ "$code" -eq 0 ]]; then
    write_status "success" "$CURRENT_STAGE" "$CURRENT_MESSAGE" "$code"
  else
    write_status "failed" "$CURRENT_STAGE" "$CURRENT_MESSAGE" "$code"
  fi
}
trap 'on_exit $?' EXIT

run_argv_step() {
  local stage="$1"
  shift
  CURRENT_STAGE="$stage"
  CURRENT_MESSAGE="running"
  echo "[RUN] ${stage}: $*" | tee -a "$RUN_LOG"
  if "$@" >>"$RUN_LOG" 2>&1; then
    echo "[OK] ${stage}" | tee -a "$RUN_LOG"
    CURRENT_MESSAGE="completed"
    return 0
  else
    local code=$?
    CURRENT_MESSAGE="failed with exit code ${code}"
    echo "[ERROR] ${stage} failed with exit code ${code}" | tee -a "$RUN_LOG"
    return "$code"
  fi
}

run_command_step() {
  local stage="$1"
  local timeout_seconds="$2"
  local command="$3"
  CURRENT_STAGE="$stage"
  CURRENT_MESSAGE="running"
  echo "[RUN] ${stage}: ${command}" | tee -a "$RUN_LOG"
  if timeout "${timeout_seconds}s" bash -lc "$command" >>"$RUN_LOG" 2>&1; then
    echo "[OK] ${stage}" | tee -a "$RUN_LOG"
    CURRENT_MESSAGE="completed"
    return 0
  else
    local code=$?
    CURRENT_MESSAGE="failed with exit code ${code}"
    echo "[WARN] ${stage} failed with exit code ${code}" | tee -a "$RUN_LOG"
    return "$code"
  fi
}

run_argv_step "preflight" ./codex_workflow/preflight.sh "$CONFIG_PATH" "$RUNTIME_JSON"
run_argv_step "input_validation" python3 codex_workflow/validate_inputs.py --config "$CONFIG_PATH" --schema codex_workflow/config.schema.json --emit-runtime "$RUNTIME_JSON"

MODE="$(python3 - <<'PY' "$RUNTIME_JSON"
import json, pathlib, sys
runtime = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
print(runtime['workflow']['mode'])
PY
)"

if [[ "$MODE" == "validate_only" ]]; then
  CURRENT_STAGE="final_output"
  CURRENT_MESSAGE="validation-only mode complete"
  echo "[OK] workflow complete (validate_only)"
  exit 0
fi

mapfile -t STEP_LINES < <(python3 - <<'PY' "$RUNTIME_JSON"
import json, pathlib, sys
runtime = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
for step in runtime['execution']['steps']:
    if step['enabled']:
        print(f"{step['id']}\t{step['retry_count']}\t{step['timeout_seconds']}\t{step['command']}")
for cmd in runtime['verification']['commands']:
    print(f"VERIFY\t0\t60\t{cmd}")
PY
)

for line in "${STEP_LINES[@]}"; do
  IFS=$'\t' read -r STEP_ID RETRIES STEP_TIMEOUT STEP_CMD <<<"$line"
  ATTEMPT=0
  SUCCESS=0
  while [[ "$ATTEMPT" -le "$RETRIES" ]]; do
    ATTEMPT=$((ATTEMPT + 1))
    STAGE_NAME="${STEP_ID}.attempt_${ATTEMPT}"
    if run_command_step "$STAGE_NAME" "$STEP_TIMEOUT" "$STEP_CMD"; then
      SUCCESS=1
      break
    fi
  done

  if [[ "$SUCCESS" -ne 1 ]]; then
    CURRENT_STAGE="$STEP_ID"
    CURRENT_MESSAGE="all attempts failed"
    exit 30
  fi
done

CURRENT_STAGE="final_output"
CURRENT_MESSAGE="workflow complete"
echo "[OK] workflow complete"
