#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-codex_workflow/config.yaml}"
RUNTIME_JSON="codex_workflow/out/runtime.contract.json"
STATUS_JSON="codex_workflow/out/status.json"
RUN_LOG="codex_workflow/out/run.log"

mkdir -p codex_workflow/out codex_workflow/out/logs
: > "$RUN_LOG"

write_status() {
  local result="$1"
  local stage="$2"
  local message="$3"
  cat > "$STATUS_JSON" <<JSON
{
  "result": "$result",
  "stage": "$stage",
  "message": "$message",
  "config_path": "$CONFIG_PATH",
  "runtime_contract": "$RUNTIME_JSON",
  "run_log": "$RUN_LOG"
}
JSON
}

run_cmd() {
  local stage="$1"
  local cmd="$2"
  echo "[RUN] ${stage}: ${cmd}" | tee -a "$RUN_LOG"
  if bash -lc "$cmd" >>"$RUN_LOG" 2>&1; then
    echo "[OK] ${stage}" | tee -a "$RUN_LOG"
    return 0
  fi
  local code=$?
  echo "[ERROR] ${stage} failed with exit code ${code}" | tee -a "$RUN_LOG"
  write_status "failed" "$stage" "command failed with exit code ${code}"
  exit "$code"
}

write_status "running" "preflight" "workflow started"
run_cmd "preflight" "./codex_workflow/preflight.sh '$CONFIG_PATH' '$RUNTIME_JSON'"
run_cmd "input_validation" "python3 codex_workflow/validate_inputs.py --config '$CONFIG_PATH' --schema codex_workflow/config.schema.json --emit-runtime '$RUNTIME_JSON'"

MODE="$(python3 - <<'PY' "$RUNTIME_JSON"
import json, pathlib, sys
runtime = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
print(runtime['workflow']['mode'])
PY
)"

if [[ "$MODE" == "validate_only" ]]; then
  write_status "success" "final_output" "validation-only mode complete"
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
    echo "[RUN] ${STEP_ID}.attempt_${ATTEMPT}: ${STEP_CMD}" | tee -a "$RUN_LOG"
    if timeout "${STEP_TIMEOUT}s" bash -lc "$STEP_CMD" >>"$RUN_LOG" 2>&1; then
      echo "[OK] ${STEP_ID}.attempt_${ATTEMPT}" | tee -a "$RUN_LOG"
      SUCCESS=1
      break
    fi
    CODE=$?
    echo "[WARN] ${STEP_ID}.attempt_${ATTEMPT} failed with exit code ${CODE}" | tee -a "$RUN_LOG"
  done

  if [[ "$SUCCESS" -ne 1 ]]; then
    write_status "failed" "$STEP_ID" "all attempts failed"
    exit 30
  fi
done

write_status "success" "final_output" "workflow complete"
echo "[OK] workflow complete"
