#!/usr/bin/env bash
# openclaw install-service — render and reconcile /etc/systemd/system/openclaw.service
# Usage:
#   sudo ./scripts/pi/install_service.sh [--root PATH] [--user USER] [--group GROUP] [--env-file PATH] [--restart]
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: must run as root. Use: sudo ./scripts/pi/install_service.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEMPLATE_PATH="${DEFAULT_ROOT}/deploy/systemd/openclaw.service.template"
SERVICE_DST="/etc/systemd/system/openclaw.service"

OPENCLAW_ROOT="${OPENCLAW_ROOT:-${DEFAULT_ROOT}}"
OPENCLAW_USER="${OPENCLAW_USER:-$(stat -c '%U' "${DEFAULT_ROOT}")}"
OPENCLAW_GROUP="${OPENCLAW_GROUP:-$(stat -c '%G' "${DEFAULT_ROOT}")}"
OPENCLAW_ENV_FILE="${OPENCLAW_ENV_FILE:-${OPENCLAW_ROOT}/.env}"
RESTART_AFTER_INSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      OPENCLAW_ROOT="$2"
      shift 2
      ;;
    --user)
      OPENCLAW_USER="$2"
      shift 2
      ;;
    --group)
      OPENCLAW_GROUP="$2"
      shift 2
      ;;
    --env-file)
      OPENCLAW_ENV_FILE="$2"
      shift 2
      ;;
    --restart)
      RESTART_AFTER_INSTALL=1
      shift
      ;;
    *)
      echo "ERROR: unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ ! -f "${TEMPLATE_PATH}" ]]; then
  echo "ERROR: missing template: ${TEMPLATE_PATH}"
  exit 1
fi

if [[ ! -f "${OPENCLAW_ROOT}/.venv/bin/python" ]]; then
  echo "ERROR: venv not found at ${OPENCLAW_ROOT}/.venv"
  echo "Run ./scripts/pi/install.sh first"
  exit 1
fi

if [[ ! -f "${OPENCLAW_ROOT}/config.yaml" ]]; then
  echo "ERROR: config.yaml not found at ${OPENCLAW_ROOT}/config.yaml"
  echo "Run: cp config.yaml.example config.yaml and configure it"
  exit 1
fi

tmp_file="$(mktemp)"
trap 'rm -f "${tmp_file}"' EXIT

sed \
  -e "s|{{OPENCLAW_ROOT}}|${OPENCLAW_ROOT}|g" \
  -e "s|{{OPENCLAW_USER}}|${OPENCLAW_USER}|g" \
  -e "s|{{OPENCLAW_GROUP}}|${OPENCLAW_GROUP}|g" \
  -e "s|{{OPENCLAW_ENV_FILE}}|${OPENCLAW_ENV_FILE}|g" \
  "${TEMPLATE_PATH}" > "${tmp_file}"

install -m 0644 "${tmp_file}" "${SERVICE_DST}"
systemd-analyze verify "${SERVICE_DST}"
systemctl daemon-reload
systemctl enable openclaw

if [[ "${RESTART_AFTER_INSTALL}" -eq 1 ]]; then
  systemctl restart openclaw
fi

echo ""
echo "=== openclaw.service reconciled ==="
echo "Unit path      : ${SERVICE_DST}"
echo "Runtime root   : ${OPENCLAW_ROOT}"
echo "User/Group     : ${OPENCLAW_USER}:${OPENCLAW_GROUP}"
echo "EnvironmentFile: ${OPENCLAW_ENV_FILE}"
echo ""
echo "Verify live unit:"
echo "  sudo systemctl cat openclaw.service"
echo "  sudo systemctl show openclaw.service -p User -p EnvironmentFile -p WorkingDirectory -p FragmentPath"
echo "  sudo cat /etc/systemd/system/openclaw.service"
