#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-codex_workflow/config.yaml}"

error() {
  echo "[ERROR] $1" >&2
  exit "${2:-1}"
}

[ -f "$CONFIG_PATH" ] || error "Config file not found: $CONFIG_PATH" 10
command -v python3 >/dev/null 2>&1 || error "Missing dependency: python3" 11
command -v git >/dev/null 2>&1 || error "Missing dependency: git" 12

REPO_ROOT=$(python3 - <<'PY' "$CONFIG_PATH"
import pathlib, sys
p = pathlib.Path(sys.argv[1])
repo = None
for line in p.read_text(encoding='utf-8').splitlines():
    s=line.strip()
    if s.startswith('repo_root:'):
        repo=s.split(':',1)[1].strip()
        break
if not repo:
    raise SystemExit(2)
print(pathlib.Path(repo).resolve())
PY
) || error "Unable to parse repo_root from $CONFIG_PATH" 13

[ -d "$REPO_ROOT" ] || error "repo_root is not a directory: $REPO_ROOT" 14
cd "$REPO_ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  error "repo_root is not a git repository: $REPO_ROOT" 15
fi

if [ "$(git rev-parse --show-toplevel)" != "$REPO_ROOT" ]; then
  error "repo_root mismatch with git toplevel" 16
fi

REQUIRE_CLEAN=$(python3 - <<'PY' "$CONFIG_PATH"
import sys, pathlib
for line in pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
    s=line.strip()
    if s.startswith('require_clean_git:'):
        print(s.split(':',1)[1].strip().lower())
        break
else:
    print('true')
PY
)

if [ "$REQUIRE_CLEAN" = "true" ] && [ -n "$(git status --porcelain)" ]; then
  error "Git workspace is dirty and require_clean_git=true" 17
fi

echo "[OK] preflight complete"
