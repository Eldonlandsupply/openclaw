#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=scripts/ngrok/_common.sh
. "$SCRIPT_DIR/_common.sh"

ngrok_load_env
ngrok_require_command ngrok

config_path=$(ngrok_config_path)
http_port=${OPENCLAW_TUNNEL_PORT:-18789}
ssh_port=${OPENCLAW_SSH_PORT:-22}

ngrok_note "Binary: $(command -v ngrok)"
ngrok_note "Version: $(ngrok version | head -n 1)"

[ -f "$config_path" ] || ngrok_fail "Missing ngrok config: $config_path"
ngrok_config_has_authtoken || ngrok_fail 'Config exists but no authtoken is configured'

ngrok config check --config "$config_path" >/dev/null 2>&1 || ngrok_fail 'ngrok config check failed'
ngrok_note 'Config check passed'

if ngrok_listening_on_port "$http_port"; then
  ngrok_note "HTTP upstream listening on :$http_port"
else
  ngrok_warn "HTTP upstream is not listening on :$http_port"
fi

if ngrok_listening_on_port "$ssh_port"; then
  ngrok_note "SSH upstream listening on :$ssh_port"
else
  ngrok_warn "SSH upstream is not listening on :$ssh_port"
fi

if ngrok service status >/dev/null 2>&1; then
  ngrok_note 'Service status command is available'
else
  ngrok_warn 'ngrok service status did not report success. Service mode may not be installed yet.'
fi

ngrok_note 'Validation completed'
