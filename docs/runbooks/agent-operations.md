# Agent Operations Reference

This file holds operator detail intentionally kept out of root `AGENTS.md`.
Use it when the task touches the matching domain.

## VM and remote ops

- exe.dev access: `ssh exe.dev`, then `ssh <vm-name>`.
- If SSH is flaky, use the exe.dev web terminal or Shelley, keep long-running work in `tmux`.
- Update global install: `sudo npm i -g openclaw@latest`.
- Set config with `openclaw config set ...`; ensure `gateway.mode=local` where required.
- Discord tokens are stored as the raw token only, not `DISCORD_BOT_TOKEN=...`.
- Gateway restart pattern:
  ```bash
  pkill -9 -f openclaw-gateway || true
  nohup openclaw gateway run --bind loopback --port 18789 --force > /tmp/openclaw-gateway.log 2>&1 &
  ```
- Verify with:
  ```bash
  openclaw channels status --probe
  ss -ltnp | rg 18789
  tail -n 120 /tmp/openclaw-gateway.log
  ```
- Signal “update fly” shortcut:
  ```bash
  fly ssh console -a flawd-bot -C "bash -lc 'cd /data/clawd/openclaw && git pull --rebase origin main'"
  fly machines restart e825232f34d058 -a flawd-bot
  ```

## Release and publish ops

- Read `docs/reference/RELEASING.md` and `docs/platforms/mac/release.md` before release work.
- Version locations:
  - `package.json`
  - `apps/android/app/build.gradle.kts`
  - `apps/ios/Sources/Info.plist`
  - `apps/ios/Tests/Info.plist`
  - `apps/macos/Sources/OpenClaw/Resources/Info.plist`
  - `docs/install/updating.md`
  - `docs/platforms/mac/release.md`
  - Peekaboo Xcode project/version files
- “Bump version everywhere” means all locations above except `appcast.xml`.
- `src/canvas-host/a2ui/.bundle.hash` is auto-generated. Regenerate only with `pnpm canvas:a2ui:bundle` or `scripts/bundle-a2ui.sh`, and commit it separately.
- Signing/notary keys are managed outside the repo.
- Required notary env vars: `APP_STORE_CONNECT_ISSUER_ID`, `APP_STORE_CONNECT_KEY_ID`, `APP_STORE_CONNECT_API_KEY_P8`.

## NPM publish with 1Password

- Use the 1Password skill.
- Run all `op` commands inside a fresh `tmux` session.
- Sign in:
  ```bash
  eval "$(op signin --account my.1password.com)"
  ```
- OTP:
  ```bash
  op read 'op://Private/Npmjs/one-time password?attribute=otp'
  ```
- Publish:
  ```bash
  npm publish --access public --otp="<otp>"
  ```
- Verify without touching local npmrc:
  ```bash
  npm view <pkg> version --userconfig "$(mktemp)"
  ```
- Kill the tmux session after publish.

## macOS and mobile specifics

- Gateway runs as the menubar app, no separate LaunchAgent/helper label.
- Restart via the app or `scripts/restart-mac.sh`.
- Verify or inspect with `launchctl print gui/$UID | grep openclaw`.
- Kill temporary tunnels before handoff.
- Use `./scripts/clawlog.sh` for unified logs.
- “Restart iOS/Android apps” means rebuild, reinstall, relaunch.
- Before simulator use, check for connected real devices.
- iOS Team ID lookup:
  ```bash
  security find-identity -p codesigning -v
  defaults read com.apple.dt.Xcode IDEProvisioningTeamIdentifiers
  ```

## Session logs and messaging

- Session files: `~/.openclaw/agents/<agentId>/sessions/*.jsonl`.
- If the log is on another machine, SSH via Tailscale and read the same path there.
- Never send streaming or partial replies to WhatsApp or Telegram, only final replies.
- Voice wake forwarder command template must remain:
  ```bash
  openclaw-mac agent --message "${text}" --thinking low
  ```
- Ensure launchd PATH includes standard system paths and the pnpm bin directory.
- For `openclaw message send` payloads containing `!`, use a heredoc.

## Misc repo-specific guardrails

- Vocabulary: “makeup” means “mac app”.
- If shared guardrails are present locally, review them before diverging.
- For bug investigations, read relevant local code and dependency source before concluding.
