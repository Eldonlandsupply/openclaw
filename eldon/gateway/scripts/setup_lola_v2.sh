#!/bin/bash
# Lola v2 setup script — run on the Pi as root
# Installs systemd timer for daily briefing, creates lola store dir

set -e

echo "=== Lola v2 setup ==="

# 1. Store directory
mkdir -p /opt/openclaw/.lola
chmod 700 /opt/openclaw/.lola

# 2. Install briefing timer
cp /opt/openclaw/eldon/deploy/systemd/lola-briefing.service /etc/systemd/system/
cp /opt/openclaw/eldon/deploy/systemd/lola-briefing.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable lola-briefing.timer
systemctl start lola-briefing.timer

echo "Briefing timer status:"
systemctl status lola-briefing.timer --no-pager

# 3. Restart gateway
systemctl restart openclaw
echo "Gateway restarted."

# 4. Quick health check
sleep 2
curl -s http://localhost:8443/health | python3 -m json.tool || true
curl -s http://localhost:8443/lola/status | python3 -m json.tool || true

echo "=== Done ==="
