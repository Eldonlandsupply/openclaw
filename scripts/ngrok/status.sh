#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=scripts/ngrok/_common.sh
. "$SCRIPT_DIR/_common.sh"

ngrok_load_env
ngrok_require_command ngrok

config_path=$(ngrok_config_path)
ngrok_note "Version: $(ngrok version | head -n 1)"
ngrok_note "Config path: $config_path"
ngrok_note "Config present: $( [ -f "$config_path" ] && printf yes || printf no )"
ngrok_note "Authtoken present: $( ngrok_config_has_authtoken && printf yes || printf no )"

if [ -f "$config_path" ]; then
  if ngrok config check --config "$config_path" >/dev/null 2>&1; then
    ngrok_note 'Config check: ok'
  else
    ngrok_warn 'Config check failed'
  fi
fi

if ngrok service status >/dev/null 2>&1; then
  ngrok service status
elif command -v systemctl >/dev/null 2>&1; then
  systemctl status ngrok --no-pager || true
else
  ngrok_warn 'Could not determine service status with ngrok service status or systemctl'
fi
