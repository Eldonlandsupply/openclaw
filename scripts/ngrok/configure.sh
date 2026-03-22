#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=scripts/ngrok/_common.sh
. "$SCRIPT_DIR/_common.sh"

ngrok_load_env
ngrok_require_command ngrok
ngrok_require_env NGROK_AUTHTOKEN

config_path=$(ngrok_config_path)
config_dir=$(dirname "$config_path")

ngrok_mkdir_private "$config_dir"

if [ ! -f "$config_path" ]; then
  ngrok_note "Creating local config from template at $config_path"
  ngrok_generate_config_from_template
else
  chmod 600 "$config_path"
fi

if ngrok config add-authtoken "$NGROK_AUTHTOKEN" --config "$config_path" >/dev/null 2>&1; then
  :
elif ngrok authtoken "$NGROK_AUTHTOKEN" --config "$config_path" >/dev/null 2>&1; then
  :
else
  ngrok_fail 'Unable to add authtoken with the installed ngrok CLI'
fi

ngrok_note "Config path: $config_path"
ngrok_note "Authtoken: $(ngrok_redact "$NGROK_AUTHTOKEN")"
ngrok_note 'Next step: edit endpoint names/domains if needed, then run scripts/ngrok/validate.sh'
