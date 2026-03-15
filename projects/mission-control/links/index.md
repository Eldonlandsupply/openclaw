# Mission Control — Project Links

## GitHub

- **Source directory:** `mission-control/` (repo root)
- **Project binding:** `projects/mission-control/`
- **Open issues:** https://github.com/Eldonlandsupply/openclaw/issues?q=label%3Amission-control

## Documentation

- Gateway WebSocket protocol: `docs/gateway/protocol.md`
- Gateway configuration reference: `docs/gateway/configuration-reference.md`
- Web control UI docs: `docs/web/control-ui.md`
- Dashboard docs: `docs/web/dashboard.md`
- CLI dashboard: `docs/cli/dashboard.md`

## Related Repo Work

- `src/gateway/control-ui.ts` — Gateway server-side control UI asset serving
- `src/gateway/server-methods/` — All gateway RPC methods Mission Control calls
- `ui/` — Main OpenClaw web UI (separate from Mission Control; uses the same gateway)

## External

- OpenClaw upstream: https://github.com/openclaw/openclaw
- Gateway protocol docs: see `docs/gateway/protocol.md`

## Notes

- Mission Control is intentionally separate from `ui/` — it is a lightweight standalone
  operator tool, not a full React application. This keeps it zero-dependency and
  directly openable from the filesystem.
- Future: once the projects registry is consumed by the gateway, Mission Control
  should gain a Projects view that renders `projects/index.yaml`.
