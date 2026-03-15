# Runbook: Create an Agent via Mission Control

**Trigger:** Operator wants to add a new agent to the OpenClaw fleet.  
**Expected outcome:** Agent appears in the Agents view and in `agents.list`.

## Steps

1. Navigate to the **Agents** view
2. Click **+ New Agent**
3. Fill in the form:
   - **Name** (required): Human-readable name, e.g. "Research Agent"
   - **Workspace** (optional): Full path where agent files live, e.g. `~/openclaw/workspaces/research`
   - **Emoji** (optional): Single emoji for visual identity
   - **Model** (optional): Override model for this agent, e.g. `claude-opus-4-5`
4. Click **Create**
5. Confirm agent appears in the list
6. Click **Files** to open the file editor and create `AGENTS.md`, `IDENTITY.md`, etc.

## After Creation

- Open **Files** → create or paste your `AGENTS.md` system prompt
- Open **Policy** to configure tool allowlist and sandbox settings
- Test by sending a message to the agent via a connected channel

## Notes

- Agent ID is auto-generated from the name; it cannot be changed after creation
- Workspace defaults to `~/.openclaw/workspaces/<agent-id>` if not specified
- Files created via Mission Control are written to the gateway's filesystem
