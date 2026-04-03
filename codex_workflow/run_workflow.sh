#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-codex_workflow/config.yaml}"
OUT_DIR="$(python3 - <<'PY' "$CONFIG_PATH"
import pathlib, sys
out='codex_workflow/out'
for line in pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
    s=line.strip()
    if s.startswith('output_dir:'):
        out=s.split(':',1)[1].strip()
print(out)
PY
)"

mkdir -p "$OUT_DIR"
STATUS_JSON="$OUT_DIR/status.json"
RUN_LOG="$OUT_DIR/run.log"

: > "$RUN_LOG"

run_step() {
  local id="$1"
  local cmd="$2"
  echo "[RUN] $id :: $cmd" | tee -a "$RUN_LOG"
  if bash -lc "$cmd" >>"$RUN_LOG" 2>&1; then
    echo "[OK] $id" | tee -a "$RUN_LOG"
    return 0
  else
    code=$?
    echo "[ERROR] $id failed with exit code $code" | tee -a "$RUN_LOG"
    return "$code"
  fi
}

run_step preflight "./codex_workflow/preflight.sh $CONFIG_PATH"
run_step validate "python3 codex_workflow/validate_inputs.py --config $CONFIG_PATH --schema codex_workflow/config.schema.json"
run_step smoke "./codex_workflow/smoke_test.sh"

cat > "$STATUS_JSON" <<JSON
{
  "result": "success",
  "config": "$CONFIG_PATH",
  "log": "$RUN_LOG"
}
JSON

echo "[OK] workflow complete"
