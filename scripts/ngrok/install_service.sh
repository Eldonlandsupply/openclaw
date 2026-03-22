#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=scripts/ngrok/_common.sh
. "$SCRIPT_DIR/_common.sh"

ngrok_load_env
ngrok_require_command ngrok

config_path=$(ngrok_config_path)
[ -f "$config_path" ] || ngrok_fail "Missing ngrok config at $config_path. Run scripts/ngrok/configure.sh first."
ngrok_config_has_authtoken || ngrok_fail 'Config exists, but no authtoken was found. Run scripts/ngrok/configure.sh first.'

install_cmd=(ngrok service install --config "$config_path")
start_cmd=(ngrok service start)

ngrok_note "Installing ngrok service with config: $config_path"
if "${install_cmd[@]}" >/dev/null 2>&1; then
  :
elif sudo "${install_cmd[@]}" >/dev/null 2>&1; then
  :
else
  ngrok_fail 'ngrok service install failed'
fi

if "${start_cmd[@]}" >/dev/null 2>&1; then
  :
elif sudo "${start_cmd[@]}" >/dev/null 2>&1; then
  :
else
  ngrok_warn 'ngrok service was installed, but service start did not succeed automatically'
fi

ngrok_note 'Service install attempted successfully'
ngrok_note 'Next step: run scripts/ngrok/status.sh and reboot once to confirm persistence'
