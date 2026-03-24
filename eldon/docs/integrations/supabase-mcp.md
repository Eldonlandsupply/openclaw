# Supabase MCP Integration

OpenClaw connects to Supabase via the **official hosted MCP server** at
`https://mcp.supabase.com`. No local Supabase install is required.

This is an **external service integration** — there is no Supabase-specific Python code
in the OpenClaw runtime. The integration lives entirely in:

- `skills/supabase-mcp/SKILL.md` — teaches the agent when and how to use the MCP server
- `eldon/config/env.example` — documents the required env vars
- This doc — setup, security, and upgrade notes

---

## Architecture decision

**Option chosen: external service + workspace skill only.**

Supabase MCP is a hosted HTTP MCP server. It requires no local binary, no daemon process,
and no Python wrapper. The correct integration point is the skill layer plus env config.
Adding Python integration code to the `eldon/` runtime would be unnecessary coupling with
no architectural benefit.

---

## Required env vars

| Variable | Description |
|----------|-------------|
| `SUPABASE_ACCESS_TOKEN` | Personal access token from https://supabase.com/dashboard/account/tokens |
| `SUPABASE_PROJECT_REF` | Project ID from Supabase Dashboard → Settings → General |

Set in `/opt/openclaw/.env` (Pi) or local `.env`:

```env
SUPABASE_ACCESS_TOKEN=sbp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SUPABASE_PROJECT_REF=abcdefghijklmnop
```

Neither value should ever be committed to the repo.

---

## openclaw.json wiring

Add to `~/.openclaw/openclaw.json` to inject credentials per agent run:

```json5
{
  skills: {
    entries: {
      "supabase-mcp": {
        enabled: true,
        env: {
          SUPABASE_ACCESS_TOKEN: "sbp_...",
          SUPABASE_PROJECT_REF: "abcdefghijklmnop",
        },
      },
    },
  },
}
```

---

## Recommended MCP URL (read-only, project-scoped)

```
https://mcp.supabase.com/mcp?project_ref=<SUPABASE_PROJECT_REF>&read_only=true
```

Use this URL in any MCP client configuration. For OpenClaw, the skill handles URL
construction — the agent is instructed to build the URL from env vars.

---

## Testing the connection

From the Pi or local machine, verify the token is valid:

```bash
curl -s -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN"   "https://api.supabase.com/v1/projects" | python3 -m json.tool | head -20
```

Expected: JSON array of your projects. If you get 401, the token is invalid or expired.

To test the MCP endpoint directly:

```bash
curl -s -X POST   -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN"   -H "Content-Type: application/json"   -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'   "https://mcp.supabase.com/mcp?project_ref=$SUPABASE_PROJECT_REF&read_only=true"
```

Expected: JSON-RPC response with a `tools` array.

---

## Upgrade path

The Supabase MCP server is maintained by Supabase and updated automatically at
`https://mcp.supabase.com`. No repo changes are needed to pick up upstream updates.

To update the skill docs if the tool surface changes:

1. Review https://github.com/supabase-community/supabase-mcp for changelog
2. Update `skills/supabase-mcp/SKILL.md` tool list if new tools were added
3. Commit to `Eldonlandsupply/openclaw` — no Python changes required

---

## Security checklist

- [ ] `SUPABASE_ACCESS_TOKEN` is in `.env`, not committed to repo
- [ ] `.gitignore` includes `.env`
- [ ] Using `read_only=true` in MCP URL unless writes are explicitly needed
- [ ] Using `project_ref` to scope to one project (not all projects)
- [ ] Connected to a dev/staging project, not production (recommended)
- [ ] MCP client approval mode is enabled (agent asks before each tool call)
