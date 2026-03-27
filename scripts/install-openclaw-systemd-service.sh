#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="openclaw"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
RUN_USER="${1:-pi}"
RUN_GROUP="${2:-$RUN_USER}"
BASE_DIR="${3:-/opt/openclaw}"
APP_DIR="${BASE_DIR}/eldon"
ENV_FILE="${BASE_DIR}/.env"
PYTHON_BIN="${BASE_DIR}/.venv/bin/python"
CONFIG_PATH="${APP_DIR}/config/config.yaml"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "ERROR: systemctl not found. This host is not systemd-based." >&2
  exit 1
fi

if [ ! -d /run/systemd/system ]; then
  echo "ERROR: systemd is not PID 1 in this environment. Run this on the target host." >&2
  exit 1
fi

if ! id "$RUN_USER" >/dev/null 2>&1; then
  echo "ERROR: user '$RUN_USER' does not exist." >&2
  exit 1
fi

if ! getent group "$RUN_GROUP" >/dev/null 2>&1; then
  echo "ERROR: group '$RUN_GROUP' does not exist." >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: missing environment file: $ENV_FILE" >&2
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "ERROR: missing python executable: $PYTHON_BIN" >&2
  exit 1
fi

if [ ! -f "$CONFIG_PATH" ]; then
  echo "ERROR: missing config file: $CONFIG_PATH" >&2
  exit 1
fi

if [ ! -d "${BASE_DIR}/data" ]; then
  install -d -o "$RUN_USER" -g "$RUN_GROUP" "${BASE_DIR}/data"
fi

if [ ! -d "${BASE_DIR}/.data" ]; then
  install -d -o "$RUN_USER" -g "$RUN_GROUP" "${BASE_DIR}/.data"
fi

cat <<UNIT | sudo tee "$SERVICE_PATH" >/dev/null
[Unit]
Description=OpenClaw Agent Runtime
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${APP_DIR}
Environment=PYTHONPATH=src
EnvironmentFile=${ENV_FILE}
ExecStart=${PYTHON_BIN} -m openclaw.main ${CONFIG_PATH}
Restart=always
RestartSec=5
TimeoutStopSec=20
StandardOutput=journal
StandardError=journal
SyslogIdentifier=openclaw
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=${BASE_DIR}/data
ReadWritePaths=${BASE_DIR}/.data

[Install]
WantedBy=multi-user.target
UNIT

sudo chown "$RUN_USER:$RUN_GROUP" "$ENV_FILE"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager -n 30
sudo journalctl -u "$SERVICE_NAME" -n 30 --no-pager
