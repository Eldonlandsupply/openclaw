#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "error: not inside a git repository" >&2
  exit 1
fi

TARGET_REMOTE_URL="${1:-https://github.com/Eldonlandsupply/openclaw.git}"
CANONICAL_PATH="/opt/openclaw"

mkdir -p /opt
if [[ ! -e "$CANONICAL_PATH" ]]; then
  ln -s "$REPO_ROOT" "$CANONICAL_PATH"
  echo "created symlink: $CANONICAL_PATH -> $REPO_ROOT"
else
  echo "path already exists: $CANONICAL_PATH"
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$TARGET_REMOTE_URL"
  echo "updated remote origin to $TARGET_REMOTE_URL"
else
  git remote add origin "$TARGET_REMOTE_URL"
  echo "created remote origin with $TARGET_REMOTE_URL"
fi

git remote -v
