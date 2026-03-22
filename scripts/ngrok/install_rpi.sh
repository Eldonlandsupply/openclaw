#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=scripts/ngrok/_common.sh
. "$SCRIPT_DIR/_common.sh"

ngrok_load_env
ngrok_require_command uname
ngrok_require_command tar
ngrok_require_command install

INSTALL_METHOD=${NGROK_INSTALL_METHOD:-archive}
INSTALL_DIR=${NGROK_INSTALL_DIR:-/usr/local/bin}
ARCH=$(ngrok_detect_arch)

ngrok_note "Detected architecture: $ARCH"
ngrok_note "Install method: $INSTALL_METHOD"

if command -v ngrok >/dev/null 2>&1; then
  ngrok_note "ngrok already installed: $(ngrok version | head -n 1)"
  exit 0
fi

case "$INSTALL_METHOD" in
  archive)
    ngrok_require_command curl
    archive_url=$(ngrok_archive_url "$ARCH")
    tmp_dir=$(mktemp -d)
    trap 'rm -rf "$tmp_dir"' EXIT
    archive_path="$tmp_dir/ngrok.tgz"

    ngrok_note "Downloading ngrok archive for $ARCH"
    ngrok_note "Source URL: $archive_url"
    curl -fsSL "$archive_url" -o "$archive_path" || ngrok_fail "Archive download failed. Set NGROK_ARCHIVE_URL if ngrok changes its archive path, or retry with NGROK_INSTALL_METHOD=apt."
    tar -xzf "$archive_path" -C "$tmp_dir"
    [ -f "$tmp_dir/ngrok" ] || ngrok_fail 'Archive did not contain an ngrok binary'

    if [ -w "$INSTALL_DIR" ]; then
      install -m 0755 "$tmp_dir/ngrok" "$INSTALL_DIR/ngrok"
    else
      sudo install -m 0755 "$tmp_dir/ngrok" "$INSTALL_DIR/ngrok"
    fi
    ;;
  apt)
    ngrok_require_command curl
    ngrok_require_command tee
    ngrok_require_command apt
    if [ "$(id -u)" -ne 0 ]; then
      sudo sh -c 'curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc > /etc/apt/trusted.gpg.d/ngrok.asc'
      echo 'deb https://ngrok-agent.s3.amazonaws.com bookworm main' | sudo tee /etc/apt/sources.list.d/ngrok.list >/dev/null
      sudo apt update
      sudo apt install -y ngrok
    else
      curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc > /etc/apt/trusted.gpg.d/ngrok.asc
      echo 'deb https://ngrok-agent.s3.amazonaws.com bookworm main' > /etc/apt/sources.list.d/ngrok.list
      apt update
      apt install -y ngrok
    fi
    ;;
  *)
    ngrok_fail "Unsupported NGROK_INSTALL_METHOD: $INSTALL_METHOD"
    ;;
esac

command -v ngrok >/dev/null 2>&1 || ngrok_fail 'ngrok installation finished without a visible ngrok binary in PATH'
ngrok_note "Installed: $(ngrok version | head -n 1)"
ngrok_note 'Next step: export NGROK_AUTHTOKEN and run scripts/ngrok/configure.sh'
