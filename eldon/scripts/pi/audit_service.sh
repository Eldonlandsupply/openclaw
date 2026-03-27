#!/usr/bin/env bash
# openclaw audit-service — compare canonical rendered unit vs deployed unit and print effective values
# Usage:
#   ./scripts/pi/audit_service.sh [--root PATH] [--user USER] [--group GROUP] [--env-file PATH]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEMPLATE_PATH="${DEFAULT_ROOT}/deploy/systemd/openclaw.service.template"
SERVICE_DST="/etc/systemd/system/openclaw.service"

OPENCLAW_ROOT="${OPENCLAW_ROOT:-${DEFAULT_ROOT}}"
OPENCLAW_USER="${OPENCLAW_USER:-$(stat -c '%U' "${DEFAULT_ROOT}")}"
OPENCLAW_GROUP="${OPENCLAW_GROUP:-$(stat -c '%G' "${DEFAULT_ROOT}")}"
OPENCLAW_ENV_FILE="${OPENCLAW_ENV_FILE:-${OPENCLAW_ROOT}/.env}"

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

tmp_file="$(mktemp)"
trap 'rm -f "${tmp_file}"' EXIT

sed \
  -e "s|{{OPENCLAW_ROOT}}|${OPENCLAW_ROOT}|g" \
  -e "s|{{OPENCLAW_USER}}|${OPENCLAW_USER}|g" \
  -e "s|{{OPENCLAW_GROUP}}|${OPENCLAW_GROUP}|g" \
  -e "s|{{OPENCLAW_ENV_FILE}}|${OPENCLAW_ENV_FILE}|g" \
  "${TEMPLATE_PATH}" > "${tmp_file}"

echo "=== OpenClaw systemd audit ==="
echo "Canonical template : ${TEMPLATE_PATH}"
echo "Rendered expectation: ${tmp_file}"
echo "Deployed unit      : ${SERVICE_DST}"
echo

echo "--- Canonical values ---"
echo "User            : ${OPENCLAW_USER}"
echo "Group           : ${OPENCLAW_GROUP}"
echo "WorkingDirectory: ${OPENCLAW_ROOT}"
echo "EnvironmentFile : ${OPENCLAW_ENV_FILE}"
echo

if [[ ! -f "${SERVICE_DST}" ]]; then
  echo "ERROR: deployed unit not found at ${SERVICE_DST}"
  echo "Remediation: sudo ./scripts/pi/install_service.sh --root '${OPENCLAW_ROOT}' --user '${OPENCLAW_USER}' --group '${OPENCLAW_GROUP}' --env-file '${OPENCLAW_ENV_FILE}'"
  exit 2
fi

echo "--- Drift check (/etc vs rendered canonical) ---"
if diff -u "${tmp_file}" "${SERVICE_DST}"; then
  echo "Result: NO DRIFT"
else
  echo "Result: DRIFT DETECTED"
  echo "Remediation: sudo ./scripts/pi/install_service.sh --root '${OPENCLAW_ROOT}' --user '${OPENCLAW_USER}' --group '${OPENCLAW_GROUP}' --env-file '${OPENCLAW_ENV_FILE}' --restart"
fi
echo

echo "--- systemctl cat openclaw.service ---"
systemctl cat openclaw.service || true
echo

echo "--- systemctl show openclaw.service ---"
systemctl show openclaw.service -p User -p EnvironmentFile -p WorkingDirectory -p FragmentPath || true
echo

echo "--- readlink -f /etc/systemd/system/openclaw.service ---"
readlink -f /etc/systemd/system/openclaw.service || true
echo

echo "--- sudo-required checks ---"
echo "sudo cat /etc/systemd/system/openclaw.service"
echo "sudo systemd-analyze verify /etc/systemd/system/openclaw.service"
