#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  cat <<'USAGE'
Usage:
  mission-control-push.sh sync <manifest-json-file>
  mission-control-push.sh heartbeat <agent-slug> [state]
  mission-control-push.sh event <agent-slug> <type> <message>

Required environment variables:
  MISSION_CONTROL_BASE_URL   Example: http://localhost:8000
  MISSION_CONTROL_SECRET     Shared secret sent as X-OpenClaw-Secret
USAGE
  exit 1
fi

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
}

require_env MISSION_CONTROL_BASE_URL
require_env MISSION_CONTROL_SECRET

BASE_URL="${MISSION_CONTROL_BASE_URL%/}"
AUTH_HEADER="X-OpenClaw-Secret: ${MISSION_CONTROL_SECRET}"

cmd="$1"
shift || true

post_json() {
  local path="$1"
  local payload="$2"
  curl --fail --silent --show-error \
    -X POST \
    -H "${AUTH_HEADER}" \
    -H "Content-Type: application/json" \
    "${BASE_URL}${path}" \
    -d "${payload}"
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}

case "${cmd}" in
  sync)
    if [[ $# -ne 1 ]]; then
      echo "sync requires one argument: manifest JSON file" >&2
      exit 1
    fi
    manifest_path="$1"
    if [[ ! -f "${manifest_path}" ]]; then
      echo "Manifest file not found: ${manifest_path}" >&2
      exit 1
    fi
    curl --fail --silent --show-error \
      -X POST \
      -H "${AUTH_HEADER}" \
      -H "Content-Type: application/json" \
      "${BASE_URL}/api/v1/integrations/openclaw/agents/sync" \
      --data-binary "@${manifest_path}"
    ;;

  heartbeat)
    if [[ $# -lt 1 || $# -gt 2 ]]; then
      echo "heartbeat requires: <agent-slug> [state]" >&2
      exit 1
    fi
    slug="$1"
    state="${2:-online}"
    state_json="$(json_escape "${state}")"
    post_json "/api/v1/integrations/openclaw/agents/${slug}/heartbeat" "{\"state\":${state_json}}"
    ;;

  event)
    if [[ $# -ne 3 ]]; then
      echo "event requires: <agent-slug> <type> <message>" >&2
      exit 1
    fi
    slug="$1"
    event_type="$2"
    message="$3"
    event_type_json="$(json_escape "${event_type}")"
    message_json="$(json_escape "${message}")"
    post_json "/api/v1/integrations/openclaw/agents/${slug}/events" "{\"type\":${event_type_json},\"message\":${message_json}}"
    ;;

  *)
    echo "Unknown command: ${cmd}" >&2
    exit 1
    ;;
esac
