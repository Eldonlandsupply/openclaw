#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-codex_workflow/config.yaml}"
TMP_DIR="codex_workflow/out/smoke"
mkdir -p "$TMP_DIR"

pass_count=0
fail_count=0

run_expect_success() {
  local name="$1"
  local cmd="$2"
  if bash -lc "$cmd" >"$TMP_DIR/$name.log" 2>&1; then
    echo "[PASS] $name"
    pass_count=$((pass_count + 1))
  else
    echo "[FAIL] $name"
    fail_count=$((fail_count + 1))
  fi
}

run_expect_failure() {
  local name="$1"
  local cmd="$2"
  if bash -lc "$cmd" >"$TMP_DIR/$name.log" 2>&1; then
    echo "[FAIL] $name (unexpected success)"
    fail_count=$((fail_count + 1))
  else
    echo "[PASS] $name"
    pass_count=$((pass_count + 1))
  fi
}

run_expect_success "happy_path" "python3 codex_workflow/validate_inputs.py --config '$CONFIG_PATH' --schema codex_workflow/config.schema.json"

cp "$CONFIG_PATH" "$TMP_DIR/missing_input.yaml"
sed -i '/run_id:/d' "$TMP_DIR/missing_input.yaml"
run_expect_failure "missing_input" "python3 codex_workflow/validate_inputs.py --config '$TMP_DIR/missing_input.yaml' --schema codex_workflow/config.schema.json"

cp "$CONFIG_PATH" "$TMP_DIR/malformed_input.yaml"
sed -i 's/run-[0-9]\{8\}-[0-9]\{4\}/bad-run-id/' "$TMP_DIR/malformed_input.yaml"
run_expect_failure "malformed_input" "python3 codex_workflow/validate_inputs.py --config '$TMP_DIR/malformed_input.yaml' --schema codex_workflow/config.schema.json"

cp "$CONFIG_PATH" "$TMP_DIR/dependency_failure.yaml"
python3 - <<'PY' "$TMP_DIR/dependency_failure.yaml"
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding='utf-8')
text = text.replace('    - git', '    - missing-binary-for-smoke')
path.write_text(text, encoding='utf-8')
PY
run_expect_failure "dependency_failure" "./codex_workflow/preflight.sh '$TMP_DIR/dependency_failure.yaml' '$TMP_DIR/runtime.json'"

cat > "$TMP_DIR/results.json" <<JSON
{
  "passes": $pass_count,
  "failures": $fail_count
}
JSON

if [[ "$fail_count" -ne 0 ]]; then
  echo "[ERROR] smoke tests failed: $fail_count"
  exit 1
fi

echo "[OK] smoke tests passed: $pass_count"
