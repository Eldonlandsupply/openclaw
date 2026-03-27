# OpenClaw systemd service management

This runtime has one canonical unit source:

- `deploy/systemd/openclaw.service.template`

Do not edit `/etc/systemd/system/openclaw.service` by hand.
Always reconcile through `scripts/pi/install_service.sh`.

## Canonical deployment model

- Canonical unit source: `deploy/systemd/openclaw.service.template`
- Render and install script: `scripts/pi/install_service.sh`
- Drift audit script: `scripts/pi/audit_service.sh`
- Deployed unit path: `/etc/systemd/system/openclaw.service`

The install and audit scripts support explicit values for:

- service user (`--user`)
- service group (`--group`)
- runtime working directory (`--root`)
- `EnvironmentFile` path (`--env-file`)

This keeps installs deterministic across hosts while still allowing intentional
host-specific values.

## Install or reconcile the unit deterministically

From the `eldon/` directory:

```bash
sudo ./scripts/pi/install_service.sh \
  --root /opt/openclaw/eldon \
  --user openclaw \
  --group openclaw \
  --env-file /etc/openclaw/openclaw.env \
  --restart
```

If your host intentionally runs as `pi`, use `--user pi --group pi`.

The script always:

1. renders the canonical template with explicit values
2. writes `/etc/systemd/system/openclaw.service`
3. runs `systemd-analyze verify`
4. runs `systemctl daemon-reload`
5. enables the unit
6. optionally restarts (`--restart`)

## Drift audit workflow

Run the audit with the same expected values:

```bash
./scripts/pi/audit_service.sh \
  --root /opt/openclaw/eldon \
  --user openclaw \
  --group openclaw \
  --env-file /etc/openclaw/openclaw.env
```

The audit prints:

- canonical rendered values (`User`, `WorkingDirectory`, `EnvironmentFile`)
- `diff -u` between rendered canonical unit and deployed unit
- explicit remediation command
- current systemd effective values from `systemctl show`

## Mandatory operator verification

Use these commands to prove what systemd is loading:

```bash
sudo systemctl cat openclaw.service
sudo systemctl show openclaw.service -p User -p EnvironmentFile -p WorkingDirectory -p FragmentPath
sudo cat /etc/systemd/system/openclaw.service
sudo systemd-analyze verify /etc/systemd/system/openclaw.service
readlink -f /etc/systemd/system/openclaw.service
```

If output does not match expected values, run install/reconcile again.

## Troubleshooting path mismatches

1. Confirm actual effective path:
   - `systemctl show openclaw.service -p FragmentPath`
2. Confirm real file target:
   - `readlink -f /etc/systemd/system/openclaw.service`
3. Compare deployed vs canonical rendered:
   - `./scripts/pi/audit_service.sh ...`
4. Reconcile:
   - `sudo ./scripts/pi/install_service.sh ... --restart`
5. Confirm running state:
   - `sudo systemctl status openclaw --no-pager`
   - `sudo journalctl -u openclaw -n 100 --no-pager`
