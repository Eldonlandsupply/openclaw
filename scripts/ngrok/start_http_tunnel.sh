#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=scripts/ngrok/_common.sh
. "$SCRIPT_DIR/_common.sh"

ngrok_load_env
ngrok_require_command ngrok

PORT=${1:-${OPENCLAW_TUNNEL_PORT:-${PORT:-18789}}}
ENDPOINT_NAME=${NGROK_ENDPOINT_NAME:-openclaw-gateway}
config_path=$(ngrok_config_path)
policy_file=$(ngrok_default_traffic_policy_path)

ngrok_listening_on_port "$PORT" || ngrok_fail "Local upstream port is not listening: $PORT"

if [ -f "$config_path" ] && grep -q "name: $ENDPOINT_NAME" "$config_path"; then
  ngrok_note "Starting config-defined endpoint: $ENDPOINT_NAME"
  exec ngrok start --config "$config_path" "$ENDPOINT_NAME"
fi

cmd=(ngrok http "$PORT")
if [ -n "${OPENCLAW_NGROK_DOMAIN:-}" ]; then
  cmd+=(--url "$OPENCLAW_NGROK_DOMAIN")
fi
if [ -f "$policy_file" ] && [ "${OPENCLAW_ENABLE_IP_RESTRICTIONS:-0}" = "1" ]; then
  cmd+=(--traffic-policy-file "$policy_file")
fi

ngrok_note "Starting HTTP tunnel for localhost:$PORT"
exec "${cmd[@]}"
