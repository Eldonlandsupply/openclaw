#!/usr/bin/env bash
set -euo pipefail

TMP_DIR="codex_workflow/out/smoke"
mkdir -p "$TMP_DIR"

pass_count=0
fail_count=0

run_expect_success() {
  local name="$1"
  local cmd="$2"
  if bash -lc "$cmd" >"$TMP_DIR/$name.log" 2>&1; then
    echo "[PASS] $name"
    pass_count=$((pass_count+1))
  else
    echo "[FAIL] $name"
    fail_count=$((fail_count+1))
  fi
}

run_expect_failure() {
  local name="$1"
  local cmd="$2"
  if bash -lc "$cmd" >"$TMP_DIR/$name.log" 2>&1; then
    echo "[FAIL] $name (unexpected success)"
    fail_count=$((fail_count+1))
  else
    echo "[PASS] $name"
    pass_count=$((pass_count+1))
  fi
}

# 1) happy-path test
run_expect_success "happy_path" "python3 codex_workflow/validate_inputs.py --config codex_workflow/config.yaml --schema codex_workflow/config.schema.json"

# 2) missing-input test
cp codex_workflow/config.yaml "$TMP_DIR/missing.yaml"
sed -i '/run_id:/d' "$TMP_DIR/missing.yaml"
run_expect_failure "missing_input" "python3 codex_workflow/validate_inputs.py --config $TMP_DIR/missing.yaml --schema codex_workflow/config.schema.json"

# 3) malformed-input test
cp codex_workflow/config.yaml "$TMP_DIR/malformed.yaml"
sed -i 's/run-20260403-0001/invalid-run-id/' "$TMP_DIR/malformed.yaml"
run_expect_failure "malformed_input" "python3 codex_workflow/validate_inputs.py --config $TMP_DIR/malformed.yaml --schema codex_workflow/config.schema.json"

# 4) dependency-failure test
run_expect_failure "dependency_failure" "PATH='' ./codex_workflow/preflight.sh codex_workflow/config.yaml"

cat > "$TMP_DIR/results.json" <<JSON
{
  "passes": $pass_count,
  "failures": $fail_count
}
JSON

if [ "$fail_count" -ne 0 ]; then
  echo "[ERROR] Smoke tests failed: $fail_count"
  exit 1
fi

echo "[OK] Smoke tests passed: $pass_count"
