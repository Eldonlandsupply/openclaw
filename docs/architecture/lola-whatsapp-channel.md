---
title: "Lola WhatsApp Channel"
description: "Configuring a dedicated Lola-only WhatsApp surface in OpenClaw."
---

# Lola WhatsApp Channel

OpenClaw does **not** currently support native per-thread subagent spawning inside a single WhatsApp chat.

Best supported fallback: bind a dedicated WhatsApp group, for example `Lola | Executive Assistant`, to a dedicated agent id such as `lola`.

## Recommended design

- Keep your main WhatsApp chat routed to the default `main` agent.
- Create a dedicated WhatsApp group for Lola.
- Bind that exact group JID to the `lola` agent.
- Let OpenClaw persist Lola under the normal session store, using Lola's own agent-scoped session key.
- Optionally use a separate WhatsApp account if you want the strongest operational separation.

## Exact config

Replace the placeholder phone numbers and group JID with your real values.

```json5
{
  session: {
    store: "~/.openclaw/sessions.json",
    dmScope: "per-account-channel-peer",
  },

  agents: {
    list: [
      {
        id: "main",
        default: true,
        name: "OpenClaw",
      },
      {
        id: "lola",
        name: "Lola",
        workspace: "~/.openclaw/workspaces/lola",
        identity: {
          name: "Lola",
        },
        groupChat: {
          mentionPatterns: ["lola", "@lola"],
        },
      },
    ],
  },

  bindings: [
    {
      agentId: "lola",
      match: {
        channel: "whatsapp",
        accountId: "default",
        peer: {
          kind: "group",
          id: "120363022222222222@g.us",
        },
      },
    },
  ],

  channels: {
    whatsapp: {
      dmPolicy: "pairing",
      allowFrom: ["+15550001111"],
      groupPolicy: "allowlist",
      groupAllowFrom: ["+15550001111"],
      responsePrefix: "",
      accounts: {
        default: {
          name: "Personal WhatsApp",
          groups: {
            "120363022222222222@g.us": {
              requireMention: false,
              allowFrom: ["+15550001111", "+15550002222"],
            },
          },
        },
      },
    },
  },
}
```

## What this gives you

- **Group routing**: the dedicated WhatsApp group is routed by `bindings[].match.peer`.
- **Agent identity**: `agents.list[].name` and `agents.list[].identity.name` are set to `Lola`.
- **Persistent isolation**: group messages land in `agent:lola:whatsapp:group:<jid>`, not in the main session.
- **Reply behavior**: set `requireMention: false` for an always-on Lola group, or `true` if you want mention-gating.
- **Allowed senders**: use `channels.whatsapp.accounts.<account>.groups.<jid>.allowFrom` for the Lola group-specific sender list.

## Separate WhatsApp account option

If you want harder operational separation, configure a second WhatsApp account and bind Lola there instead of using a group on your main account.

Example changes:

```json5
{
  bindings: [
    {
      agentId: "lola",
      match: { channel: "whatsapp", accountId: "lola" },
    },
  ],
  channels: {
    whatsapp: {
      accounts: {
        lola: {
          name: "Lola WhatsApp",
          authDir: "~/.openclaw/credentials/whatsapp-lola",
          dmPolicy: "allowlist",
          allowFrom: ["+15550001111"],
        },
      },
    },
  },
}
```

That is more reliable if you want zero chance of personal-chat overlap, at the cost of another linked WhatsApp identity.

## Restart commands

```bash
pkill -9 -f openclaw-gateway || true
nohup openclaw gateway run --bind loopback --port 18789 --force > /tmp/openclaw-gateway.log 2>&1 &
openclaw channels status --probe
ss -ltnp | rg 18789
tail -n 120 /tmp/openclaw-gateway.log
```

## Test plan

1. Send a message in the `Lola | Executive Assistant` group.
2. Confirm the inbound route resolves to agent `lola`.
3. Confirm the reply is posted back into the same WhatsApp group.
4. Send a message in your main OpenClaw WhatsApp DM or another group.
5. Confirm that traffic still resolves to the default `main` agent/session.
6. Restart the gateway.
7. Send another Lola-group message and confirm the prior Lola context is still present.

## Rollback

1. Remove the Lola `bindings` entry.
2. Remove the Lola group entry from `channels.whatsapp.accounts.<account>.groups`.
3. Optionally remove the `lola` agent definition.
4. Restart the gateway.
5. If you want to discard Lola-only history too, delete the matching `agent:lola:whatsapp:group:<jid>` session from your session store backup workflow, not by ad-hoc editing on a live system.
