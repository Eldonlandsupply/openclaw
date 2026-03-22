#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=scripts/ngrok/_common.sh
. "$SCRIPT_DIR/_common.sh"

ngrok_load_env
ngrok_require_command ngrok

SSH_PORT=${1:-${OPENCLAW_SSH_PORT:-22}}
ENDPOINT_NAME=${NGROK_SSH_ENDPOINT_NAME:-openclaw-ssh}
config_path=$(ngrok_config_path)

ngrok_warn 'SSH over ngrok exposes shell access. Use this only when SSH access is required, keep accounts hardened, and prefer IP restrictions or reserved TCP addresses.'
ngrok_listening_on_port "$SSH_PORT" || ngrok_fail "Local SSH port is not listening: $SSH_PORT"

if [ -f "$config_path" ] && grep -q "name: $ENDPOINT_NAME" "$config_path"; then
  ngrok_note "Starting config-defined TCP endpoint: $ENDPOINT_NAME"
  exec ngrok start --config "$config_path" "$ENDPOINT_NAME"
fi

cmd=(ngrok tcp "$SSH_PORT")
if [ -n "${OPENCLAW_NGROK_TCP_ADDRESS:-}" ]; then
  cmd+=(--url "tcp://$OPENCLAW_NGROK_TCP_ADDRESS")
fi

ngrok_note "Starting TCP SSH tunnel for localhost:$SSH_PORT"
exec "${cmd[@]}"
