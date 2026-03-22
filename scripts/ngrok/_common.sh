#!/usr/bin/env bash

set -euo pipefail

NGROK_REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NGROK_DEFAULT_ENV_FILES=(
  "$NGROK_REPO_ROOT/.env"
  "${HOME}/.openclaw/.env"
)

ngrok_note() {
  printf '[ngrok] %s\n' "$*"
}

ngrok_warn() {
  printf '[ngrok][warn] %s\n' "$*" >&2
}

ngrok_fail() {
  printf '[ngrok][error] %s\n' "$*" >&2
  exit 1
}

ngrok_load_env() {
  local env_file line key value
  for env_file in "${NGROK_DEFAULT_ENV_FILES[@]}"; do
    if [ ! -f "$env_file" ]; then
      continue
    fi
    while IFS= read -r line || [ -n "$line" ]; do
      case "$line" in
        '' | '#'* ) continue ;;
      esac
      key=${line%%=*}
      value=${line#*=}
      if [ -z "$key" ] || [ "$key" = "$line" ]; then
        continue
      fi
      if [ -n "${!key-}" ]; then
        continue
      fi
      export "$key=$value"
    done < "$env_file"
  done
}

ngrok_require_command() {
  command -v "$1" >/dev/null 2>&1 || ngrok_fail "Required command not found: $1"
}

ngrok_require_env() {
  local var_name=$1
  [ -n "${!var_name-}" ] || ngrok_fail "Missing required environment variable: $var_name"
}

ngrok_default_config_path() {
  if [ -n "${NGROK_CONFIG_PATH-}" ]; then
    printf '%s\n' "$NGROK_CONFIG_PATH"
  elif [ -n "${XDG_CONFIG_HOME-}" ]; then
    printf '%s/ngrok/ngrok.yml\n' "$XDG_CONFIG_HOME"
  else
    printf '%s/.config/ngrok/ngrok.yml\n' "$HOME"
  fi
}

ngrok_default_traffic_policy_path() {
  if [ -n "${NGROK_TRAFFIC_POLICY_FILE-}" ]; then
    printf '%s\n' "$NGROK_TRAFFIC_POLICY_FILE"
  else
    printf '%s/config/ngrok/policies/restrict-ips.template.yml\n' "$NGROK_REPO_ROOT"
  fi
}

ngrok_config_path() {
  printf '%s\n' "$(ngrok_default_config_path)"
}

ngrok_config_dir() {
  dirname "$(ngrok_config_path)"
}

ngrok_redact() {
  local value=${1-}
  if [ -z "$value" ]; then
    printf '<unset>\n'
  elif [ ${#value} -le 8 ]; then
    printf '********\n'
  else
    printf '%s***%s\n' "${value:0:4}" "${value: -4}"
  fi
}

ngrok_detect_arch() {
  local machine=${1:-$(uname -m)}
  case "$machine" in
    aarch64 | arm64) printf 'arm64\n' ;;
    armv7l | armv7 | armhf) printf 'arm\n' ;;
    x86_64 | amd64) printf 'amd64\n' ;;
    *) ngrok_fail "Unsupported architecture: $machine" ;;
  esac
}

ngrok_archive_url() {
  local arch=$1
  if [ -n "${NGROK_ARCHIVE_URL-}" ]; then
    printf '%s\n' "$NGROK_ARCHIVE_URL"
    return 0
  fi

  case "$arch" in
    arm64) printf 'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz\n' ;;
    arm) printf 'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz\n' ;;
    amd64) printf 'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz\n' ;;
    *) ngrok_fail "No archive URL mapping for architecture: $arch" ;;
  esac
}

ngrok_config_has_authtoken() {
  local config_path
  config_path=$(ngrok_config_path)
  [ -f "$config_path" ] || return 1
  grep -Eq '^[[:space:]]*authtoken:[[:space:]]*[^[:space:]]+' "$config_path"
}

ngrok_listening_on_port() {
  local port=$1
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "( sport = :$port )" | tail -n +2 | grep -q "."
    return
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi
  ngrok_fail 'Neither ss nor lsof is available to verify local listening ports'
}

ngrok_mkdir_private() {
  mkdir -p "$1"
  chmod 700 "$1"
}

ngrok_generate_config_from_template() {
  local target_path template_path
  target_path=$(ngrok_config_path)
  template_path=${1:-$NGROK_REPO_ROOT/config/ngrok/ngrok.template.yml}
  [ -f "$template_path" ] || ngrok_fail "Missing template: $template_path"
  ngrok_mkdir_private "$(dirname "$target_path")"
  sed \
    -e "s#__OPENCLAW_HTTP_PORT__#${OPENCLAW_TUNNEL_PORT:-18789}#g" \
    -e "s#__OPENCLAW_HTTP_DOMAIN__#${OPENCLAW_NGROK_DOMAIN:-}#g" \
    -e "s#__OPENCLAW_TCP_ADDRESS__#${OPENCLAW_NGROK_TCP_ADDRESS:-}#g" \
    "$template_path" > "$target_path"
  chmod 600 "$target_path"
}
