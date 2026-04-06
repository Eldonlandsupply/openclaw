# Mission Control — Gateway API Capabilities

This document catalogs the OpenClaw gateway commands used by Mission Control.
It is the authoritative reference for what the application can and cannot do
without additional gateway feature work.

## Connection

| Command    | Description                                                                      |
| ---------- | -------------------------------------------------------------------------------- |
| `connect`  | Handshake, auth, protocol negotiation. Returns `helloData` and `serverFeatures`. |
| `snapshot` | Point-in-time overview: uptime, presence, config path, state dir.                |

## Agents

| Command             | Description                                                |
| ------------------- | ---------------------------------------------------------- |
| `agents.list`       | All configured agents + default agent ID.                  |
| `agents.create`     | Create a new agent. Params: name, workspace, emoji, model. |
| `agents.update`     | Update agent fields. Params: id + fields to change.        |
| `agents.delete`     | Remove an agent. Params: id.                               |
| `agents.files.list` | List files in an agent's workspace. Params: agentId.       |
| `agents.files.get`  | Read a file. Params: agentId, path.                        |
| `agents.files.set`  | Write a file. Params: agentId, path, content.              |

## Sessions

| Command            | Description                                     |
| ------------------ | ----------------------------------------------- |
| `sessions.list`    | All sessions with metadata.                     |
| `sessions.preview` | Preview session transcript. Params: sessionKey. |
| `sessions.reset`   | Reset a session's history. Params: sessionKey.  |
| `sessions.delete`  | Delete a session entirely. Params: sessionKey.  |

## Channels

| Command           | Description                                    |
| ----------------- | ---------------------------------------------- |
| `channels.status` | Status of all configured channel integrations. |

## Cron

| Command       | Description                                                   |
| ------------- | ------------------------------------------------------------- |
| `cron.list`   | All scheduled jobs.                                           |
| `cron.add`    | Add a cron job. Params: schedule, agentId, prompt, deliverTo. |
| `cron.run`    | Trigger a job immediately. Params: jobId.                     |
| `cron.remove` | Remove a job. Params: jobId.                                  |

## Models

| Command       | Description                                     |
| ------------- | ----------------------------------------------- |
| `models.list` | All available models from configured providers. |

## Config

| Command      | Description                                  |
| ------------ | -------------------------------------------- |
| `config.get` | Read current gateway config (full JSON).     |
| `config.set` | Write gateway config. Params: config object. |

## Logs

| Command     | Description                                                            |
| ----------- | ---------------------------------------------------------------------- |
| `logs.tail` | Paginated log tail. Params: cursor, limit. Returns lines + nextCursor. |

## Nodes

| Command      | Description              |
| ------------ | ------------------------ |
| `nodes.list` | All paired remote nodes. |

## Exec Approvals

| Command                 | Description                                   |
| ----------------------- | --------------------------------------------- |
| `execApprovals.list`    | Pending approvals queue.                      |
| `execApprovals.approve` | Approve an exec approval. Params: approvalId. |
| `execApprovals.reject`  | Reject an exec approval. Params: approvalId.  |

## Skills

| Command         | Description                                              |
| --------------- | -------------------------------------------------------- |
| `skills.list`   | All installed skills across agents.                      |
| `skills.update` | Update a skill config. Params: agentId, skillId, config. |

## Devices

| Command        | Description                       |
| -------------- | --------------------------------- |
| `devices.list` | All paired mobile/remote devices. |

## Usage

| Command          | Description                                 |
| ---------------- | ------------------------------------------- |
| `usage.sessions` | Token and cost usage aggregated by session. |

## Events (Real-time)

Mission Control receives real-time events from the gateway websocket.
Currently handled event types:

- `execApprovalRequest` — incoming approval request; adds to pending list
- `execApprovalResolved` — approval resolved; removes from pending list
- `devicePairRequest` — pairing request from a device
