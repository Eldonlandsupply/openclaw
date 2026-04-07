#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-codex_workflow/config.yaml}"
RUNTIME_JSON="${2:-codex_workflow/out/runtime.contract.json}"

fail() {
  local code="$1"
  local message="$2"
  echo "[ERROR] PREFLIGHT_FAILED: ${message}" >&2
  exit "$code"
}

[[ -f "$CONFIG_PATH" ]] || fail 10 "Config file not found: $CONFIG_PATH"
command -v python3 >/dev/null 2>&1 || fail 11 "Missing dependency: python3"
command -v bash >/dev/null 2>&1 || fail 12 "Missing dependency: bash"

python3 codex_workflow/validate_inputs.py \
  --config "$CONFIG_PATH" \
  --schema codex_workflow/config.schema.json \
  --emit-runtime "$RUNTIME_JSON" >/dev/null || fail 13 "Input validation failed"

mapfile -t PREFLIGHT_VALUES < <(python3 - <<'PY' "$RUNTIME_JSON"
import json, pathlib, sys
runtime = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
print(pathlib.Path(runtime['paths']['repo_root']).resolve())
print('true' if runtime['runtime']['require_clean_git'] else 'false')
for b in runtime['dependencies']['required_binaries']:
    print(f"bin:{b}")
PY
)

REPO_ROOT="${PREFLIGHT_VALUES[0]}"
REQUIRE_CLEAN="${PREFLIGHT_VALUES[1]}"

for entry in "${PREFLIGHT_VALUES[@]:2}"; do
  bin="${entry#bin:}"
  command -v "$bin" >/dev/null 2>&1 || fail 18 "Missing dependency binary: $bin"
done

[[ -d "$REPO_ROOT" ]] || fail 14 "paths.repo_root is not a directory: $REPO_ROOT"
cd "$REPO_ROOT"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail 15 "paths.repo_root is not inside a git worktree"
[[ "$(git rev-parse --show-toplevel)" == "$REPO_ROOT" ]] || fail 16 "paths.repo_root must equal git top-level root"

if [[ "$REQUIRE_CLEAN" == "true" ]] && [[ -n "$(git status --porcelain)" ]]; then
  fail 17 "Git workspace dirty while runtime.require_clean_git=true"
fi

echo "[OK] preflight complete"
