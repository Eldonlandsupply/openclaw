/**
 * OpenClaw Mission Control — mc.js
 * Standalone single-file WS gateway client + control plane UI.
 *
 * Protocol: OpenClaw Gateway WS (PROTOCOL_VERSION 4+)
 * All RPC via request/response frames; events push state deltas.
 */

"use strict";

// ─────────────────────────────────────────────
// 1. GATEWAY CLIENT
// ─────────────────────────────────────────────

class GatewayClient {
  constructor({ url, token, password, onEvent, onConnect, onDisconnect, onError }) {
    this.url = url;
    this.token = token;
    this.password = password;
    this.onEvent = onEvent || (() => {});
    this.onConnect = onConnect || (() => {});
    this.onDisconnect = onDisconnect || (() => {});
    this.onError = onError || (() => {});
    this.ws = null;
    this.pending = new Map();   // requestId → { resolve, reject }
    this.seq = 0;
    this.connected = false;
    this.helloData = null;
    this._reconnectTimer = null;
  }

  connect() {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);
      } catch (e) {
        reject(e);
        return;
      }

      this.ws.onopen = () => {
        // Send connect frame
        this._send({
          type: "request",
          id: this._nextId(),
          command: "connect",
          params: {
            minProtocol: 4,
            maxProtocol: 9,
            client: {
              id: "mission-control",
              displayName: "Mission Control",
              version: "1.0.0",
              platform: "web",
              mode: "control",
            },
            auth: {
              token: this.token || undefined,
              password: this.password || undefined,
            },
          },
        }, resolve, reject, true);
      };

      this.ws.onmessage = (evt) => {
        let frame;
        try { frame = JSON.parse(evt.data); }
        catch { return; }
        this._handleFrame(frame);
      };

      this.ws.onclose = (evt) => {
        this.connected = false;
        // Reject any pending requests
        for (const [, p] of this.pending) p.reject(new Error("WebSocket closed"));
        this.pending.clear();
        this.onDisconnect(evt.code, evt.reason || "closed");
      };

      this.ws.onerror = (err) => {
        this.onError(err);
        reject(err);
      };
    });
  }

  disconnect() {
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
  }

  request(command, params = {}) {
    return new Promise((resolve, reject) => {
      const id = this._nextId();
      this._send({ type: "request", id, command, params }, resolve, reject, false);
    });
  }

  _nextId() {
    return `mc-${Date.now()}-${++this.seq}`;
  }

  _send(frame, resolve, reject, isConnect) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      reject(new Error("Not connected"));
      return;
    }
    this.pending.set(frame.id, { resolve, reject, isConnect });
    this.ws.send(JSON.stringify(frame));
  }

  _handleFrame(frame) {
    if (frame.type === "response") {
      const p = this.pending.get(frame.id);
      if (!p) return;
      this.pending.delete(frame.id);
      if (frame.error) {
        p.reject(Object.assign(new Error(frame.error.message || "Gateway error"), { code: frame.error.code }));
      } else {
        if (p.isConnect) {
          this.connected = true;
          this.helloData = frame.result;
          this.onConnect(frame.result);
        }
        p.resolve(frame.result);
      }
    } else if (frame.type === "event") {
      this.onEvent(frame);
    }
  }
}


// ─────────────────────────────────────────────
// 2. APP STATE
// ─────────────────────────────────────────────

const state = {
  client: null,
  snapshot: null,
  agents: [],
  sessions: [],
  channels: {},
  cron: [],
  models: [],
  nodes: [],
  config: null,
  logLines: [],
  logCursor: 0,
  logFollowing: true,
};

let logPollInterval = null;


// ─────────────────────────────────────────────
// 3. DOM HELPERS
// ─────────────────────────────────────────────

function el(id) { return document.getElementById(id); }
function qs(sel, root = document) { return root.querySelector(sel); }

function toast(msg, type = "info", duration = 3500) {
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.textContent = msg;
  el("toast-container").appendChild(t);
  setTimeout(() => t.remove(), duration);
}

function setStatus(state_str, label) {
  const dot = el("status-dot");
  dot.className = `status-dot ${state_str}`;
  el("status-label").textContent = label;
}

function showModal(title, bodyHTML, footerHTML, onClose) {
  el("modal-title").textContent = title;
  el("modal-body").innerHTML = bodyHTML;
  el("modal-footer").innerHTML = footerHTML;
  el("modal-backdrop").classList.remove("hidden");
  const cleanup = () => {
    el("modal-backdrop").classList.add("hidden");
    if (onClose) onClose();
  };
  el("modal-close").onclick = cleanup;
  el("modal-backdrop").onclick = (e) => { if (e.target === el("modal-backdrop")) cleanup(); };
  return cleanup;
}

function fmtUptime(ms) {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

function fmtTs(ms) {
  if (!ms) return "—";
  const d = new Date(ms);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function escHtml(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}


// ─────────────────────────────────────────────
// 4. NAVIGATION
// ─────────────────────────────────────────────

const viewLoaders = {
  overview:  loadOverview,
  agents:    loadAgents,
  sessions:  loadSessions,
  channels:  loadChannels,
  cron:      loadCron,
  models:    loadModels,
  config:    loadConfig,
  logs:      loadLogs,
  nodes:     loadNodes,
};

function navigate(view) {
  document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".view").forEach(v => v.classList.add("hidden"));
  const btn = document.querySelector(`.nav-item[data-view="${view}"]`);
  if (btn) btn.classList.add("active");
  const viewEl = el(`view-${view}`);
  if (viewEl) viewEl.classList.remove("hidden");
  const loader = viewLoaders[view];
  if (loader && state.client?.connected) loader();
}


// ─────────────────────────────────────────────
// 5. OVERVIEW
// ─────────────────────────────────────────────

async function loadOverview() {
  try {
    const snap = await state.client.request("snapshot", {});
    state.snapshot = snap;

    // Stats
    const agentCount = state.agents.length;
    qs(".stat-value", el("stat-agents")).textContent = agentCount || "—";
    qs(".stat-value", el("stat-sessions")).textContent = state.sessions.length || "—";
    qs(".stat-value", el("stat-clients")).textContent = (snap.presence || []).length;
    qs(".stat-value", el("stat-uptime")).textContent = snap.uptimeMs ? fmtUptime(snap.uptimeMs) : "—";

    el("uptime-badge").textContent = snap.uptimeMs ? `up ${fmtUptime(snap.uptimeMs)}` : "—";

    // Presence
    const presEl = el("presence-list");
    const presence = snap.presence || [];
    if (presence.length === 0) {
      presEl.innerHTML = `<div class="empty-state"><strong>NO CLIENTS</strong>None connected</div>`;
    } else {
      presEl.innerHTML = presence.map(p => `
        <div class="presence-entry">
          <span class="pe-mode">${escHtml(p.mode || "?")}</span>
          <span class="pe-name">${escHtml(p.host || p.ip || "unknown")}</span>
          <span class="pe-platform">${escHtml(p.platform || "")}</span>
        </div>
      `).join("");
    }

    // Agents summary
    await loadAgentsSummary();
    const agList = el("agents-overview-list");
    if (state.agents.length === 0) {
      agList.innerHTML = `<div class="empty-state"><strong>NO AGENTS</strong>Create one in the Agents view</div>`;
    } else {
      agList.innerHTML = state.agents.map(a => `
        <div class="presence-entry">
          <span class="pe-mode">${escHtml(a.identity?.emoji || "🤖")}</span>
          <span class="pe-name">${escHtml(a.identity?.name || a.name || a.id)}</span>
          <span class="pe-platform">${escHtml(a.id)}</span>
        </div>
      `).join("");
    }

    // Gateway info sidebar
    el("gateway-info").innerHTML = [
      snap.configPath ? `cfg: ${snap.configPath.split("/").slice(-3).join("/")}` : "",
      snap.stateDir   ? `state: ${snap.stateDir.split("/").slice(-2).join("/")}` : "",
    ].filter(Boolean).join("<br>");

  } catch (e) {
    toast("Overview error: " + e.message, "error");
  }
}


// ─────────────────────────────────────────────
// 6. AGENTS
// ─────────────────────────────────────────────

async function loadAgentsSummary() {
  try {
    const res = await state.client.request("agents.list", {});
    state.agents = res.agents || [];
    state.defaultAgentId = res.defaultId;
    return res;
  } catch (e) {
    return null;
  }
}

async function loadAgents() {
  const container = el("agents-list");
  container.innerHTML = `<div class="loading-text">Loading agents…</div>`;
  try {
    const res = await state.client.request("agents.list", {});
    state.agents = res.agents || [];
    state.defaultAgentId = res.defaultId;

    if (state.agents.length === 0) {
      container.innerHTML = `<div class="empty-state"><strong>NO AGENTS</strong>Click + New Agent to create one</div>`;
      return;
    }

    container.innerHTML = state.agents.map(a => {
      const name = a.identity?.name || a.name || a.id;
      const emoji = a.identity?.emoji || "🤖";
      const isDefault = a.id === res.defaultId;
      return `
        <div class="agent-card ${isDefault ? "is-default" : ""}" data-agent-id="${escHtml(a.id)}">
          <div class="agent-card-header">
            <div class="agent-avatar">${escHtml(emoji)}</div>
            <div>
              <div class="agent-name">${escHtml(name)}</div>
              <div class="agent-id">${escHtml(a.id)}</div>
            </div>
          </div>
          <div class="agent-badges">
            ${isDefault ? `<span class="chip chip-default">DEFAULT</span>` : ""}
          </div>
          <div class="agent-card-actions">
            <button class="btn-ghost sm" onclick="openAgentEdit('${escHtml(a.id)}')">Edit</button>
            <button class="btn-ghost sm" onclick="openAgentFiles('${escHtml(a.id)}')">Files</button>
            <button class="btn-danger sm" onclick="confirmDeleteAgent('${escHtml(a.id)}', '${escHtml(name)}')">Delete</button>
          </div>
        </div>
      `;
    }).join("");
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
    toast("Failed to load agents: " + e.message, "error");
  }
}

function openCreateAgent() {
  const close = showModal(
    "Create Agent",
    `<div class="modal-form">
      <div class="form-group"><label>Agent ID</label><input id="na-id" type="text" placeholder="my-agent" /></div>
      <div class="form-group"><label>Name</label><input id="na-name" type="text" placeholder="My Agent" /></div>
      <div class="form-group"><label>Workspace</label><input id="na-workspace" type="text" placeholder="~/openclaw/workspaces/my-agent" /></div>
      <div class="form-group"><label>Emoji <span class="opt">(optional)</span></label><input id="na-emoji" type="text" placeholder="🤖" /></div>
    </div>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-primary sm" id="m-create">Create</button>`,
    null
  );
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-create", el("modal")).onclick = async () => {
    const name = el("na-name").value.trim();
    const workspace = el("na-workspace").value.trim();
    const emoji = el("na-emoji").value.trim();
    if (!name || !workspace) { toast("Name and workspace required", "error"); return; }
    try {
      const res = await state.client.request("agents.create", { name, workspace, emoji: emoji || undefined });
      toast(`Agent "${res.name}" created (${res.agentId})`, "success");
      close();
      loadAgents();
    } catch (e) {
      toast("Create failed: " + e.message, "error");
    }
  };
}

async function openAgentEdit(agentId) {
  const agent = state.agents.find(a => a.id === agentId);
  if (!agent) return;
  const name = agent.identity?.name || agent.name || "";
  const emoji = agent.identity?.emoji || "";
  const close = showModal(
    `Edit Agent: ${agentId}`,
    `<div class="modal-form">
      <div class="form-group"><label>Name</label><input id="ea-name" type="text" value="${escHtml(name)}" /></div>
      <div class="form-group"><label>Emoji</label><input id="ea-emoji" type="text" value="${escHtml(emoji)}" placeholder="🤖"/></div>
      <div class="form-group"><label>Model <span class="opt">(optional)</span></label><input id="ea-model" type="text" placeholder="anthropic/claude-sonnet-4-20250514" /></div>
    </div>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-primary sm" id="m-save">Save</button>`,
    null
  );
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-save", el("modal")).onclick = async () => {
    const params = { agentId };
    const n = el("ea-name").value.trim();
    const e = el("ea-emoji").value.trim();
    const m = el("ea-model").value.trim();
    if (n) params.name = n;
    if (e) params.avatar = e;
    if (m) params.model = m;
    try {
      await state.client.request("agents.update", params);
      toast(`Agent ${agentId} updated`, "success");
      close();
      loadAgents();
    } catch (err) {
      toast("Update failed: " + err.message, "error");
    }
  };
}

async function openAgentFiles(agentId) {
  try {
    const res = await state.client.request("agents.files.list", { agentId });
    const files = res.files || [];
    const fileListHTML = files.length === 0
      ? `<div class="empty-state"><strong>NO FILES</strong>Workspace: ${escHtml(res.workspace)}</div>`
      : files.map(f => `
        <div class="presence-entry" style="cursor:pointer" onclick="openFileEdit('${escHtml(agentId)}', '${escHtml(f.name)}')">
          <span class="pe-mode" style="${f.missing ? 'background:var(--error-dim);color:var(--error)' : ''}">
            ${f.missing ? "MISSING" : "FILE"}
          </span>
          <span class="pe-name">${escHtml(f.name)}</span>
          <span class="pe-platform">${f.size != null ? (f.size/1024).toFixed(1)+"KB" : ""}</span>
        </div>
      `).join("");

    showModal(
      `Files: ${agentId}`,
      `<div style="margin-bottom:10px;font-size:12px;color:var(--text-muted);font-family:var(--font-mono)">${escHtml(res.workspace)}</div>
       <div>${fileListHTML}</div>`,
      `<button class="btn-ghost sm" id="m-close">Close</button>`,
      null
    );
    qs("#m-close", el("modal")).onclick = () => el("modal-backdrop").classList.add("hidden");
  } catch (e) {
    toast("Files error: " + e.message, "error");
  }
}

async function openFileEdit(agentId, fileName) {
  try {
    const res = await state.client.request("agents.files.get", { agentId, name: fileName });
    const content = res.file?.content || "";
    const close = showModal(
      `${agentId} / ${fileName}`,
      `<textarea id="fe-content" class="config-editor" style="height:350px">${escHtml(content)}</textarea>`,
      `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
       <button class="btn-primary sm" id="m-save">Save</button>`,
      null
    );
    qs("#m-cancel", el("modal")).onclick = close;
    qs("#m-save", el("modal")).onclick = async () => {
      const newContent = el("fe-content").value;
      try {
        await state.client.request("agents.files.set", { agentId, name: fileName, content: newContent });
        toast(`Saved ${fileName}`, "success");
        close();
      } catch (e) {
        toast("Save failed: " + e.message, "error");
      }
    };
  } catch (e) {
    toast("File load error: " + e.message, "error");
  }
}

function confirmDeleteAgent(agentId, name) {
  const close = showModal(
    "Delete Agent",
    `<p style="color:var(--text-muted)">Delete agent <strong style="color:var(--text)">${escHtml(name)}</strong> (<code style="font-family:var(--font-mono);color:var(--error)">${escHtml(agentId)}</code>)?</p>
     <p style="margin-top:10px;font-size:12px;color:var(--text-dim)">This will remove the agent config. Transcript files will not be deleted.</p>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-danger sm" id="m-delete">Delete</button>`,
    null
  );
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-delete", el("modal")).onclick = async () => {
    try {
      await state.client.request("agents.delete", { agentId, deleteFiles: false });
      toast(`Agent ${agentId} deleted`, "success");
      close();
      loadAgents();
    } catch (e) {
      toast("Delete failed: " + e.message, "error");
    }
  };
}


// ─────────────────────────────────────────────
// 7. SESSIONS
// ─────────────────────────────────────────────

async function loadSessions() {
  const container = el("sessions-list");
  container.innerHTML = `<div class="loading-text">Loading sessions…</div>`;
  try {
    const res = await state.client.request("sessions.list", {
      limit: 100,
      includeDerivedTitles: true,
      includeLastMessage: false,
    });
    const sessions = res.sessions || res || [];
    state.sessions = sessions;
    renderSessions(sessions);
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}

function renderSessions(sessions) {
  const container = el("sessions-list");
  if (!sessions || sessions.length === 0) {
    container.innerHTML = `<div class="empty-state"><strong>NO SESSIONS</strong>Sessions appear here when agents have conversations</div>`;
    return;
  }
  container.innerHTML = sessions.map(s => {
    const title = s.derivedTitle || s.label || s.key?.split(":").pop() || s.key || "—";
    return `
      <div class="session-row" onclick="openSessionDetail('${escHtml(s.key)}')">
        <span class="session-key">${escHtml(s.key || "")}</span>
        <span class="session-agent">${escHtml(s.agentId || "—")}</span>
        <span class="session-title">${escHtml(title)}</span>
        <span class="session-ts">${fmtTs(s.updatedAtMs || s.createdAtMs)}</span>
        <span class="session-actions">
          <button class="btn-ghost sm" onclick="event.stopPropagation(); confirmDeleteSession('${escHtml(s.key)}')">✕</button>
        </span>
      </div>
    `;
  }).join("");
}

async function openSessionDetail(sessionKey) {
  try {
    const res = await state.client.request("sessions.preview", { keys: [sessionKey], maxChars: 2000 });
    const preview = (res.previews || [])[0] || {};
    showModal(
      `Session: ${sessionKey}`,
      `<div style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);white-space:pre-wrap;max-height:400px;overflow-y:auto;background:var(--bg);padding:12px;border-radius:4px">${escHtml(preview.content || "(empty)")}</div>`,
      `<button class="btn-ghost sm" id="m-close">Close</button>
       <button class="btn-danger sm" id="m-reset">Reset</button>`,
      null
    );
    qs("#m-close", el("modal")).onclick = () => el("modal-backdrop").classList.add("hidden");
    qs("#m-reset", el("modal")).onclick = async () => {
      try {
        await state.client.request("sessions.reset", { key: sessionKey });
        toast(`Session reset: ${sessionKey}`, "success");
        el("modal-backdrop").classList.add("hidden");
        loadSessions();
      } catch (e) { toast("Reset failed: " + e.message, "error"); }
    };
  } catch (e) {
    toast("Session detail error: " + e.message, "error");
  }
}

function confirmDeleteSession(key) {
  const close = showModal(
    "Delete Session",
    `<p style="color:var(--text-muted)">Delete session <code style="font-family:var(--font-mono);color:var(--error)">${escHtml(key)}</code>?</p>
     <p style="margin-top:10px;font-size:12px;color:var(--text-dim)">Optionally delete the transcript file too.</p>
     <label style="display:flex;align-items:center;gap:8px;margin-top:12px;font-size:12px">
       <input type="checkbox" id="del-transcript"> Delete transcript file
     </label>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-danger sm" id="m-delete">Delete</button>`,
    null
  );
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-delete", el("modal")).onclick = async () => {
    const dt = el("del-transcript")?.checked || false;
    try {
      await state.client.request("sessions.delete", { key, deleteTranscript: dt });
      toast(`Session deleted`, "success");
      close();
      loadSessions();
    } catch (e) { toast("Delete failed: " + e.message, "error"); }
  };
}


// ─────────────────────────────────────────────
// 8. CHANNELS
// ─────────────────────────────────────────────

async function loadChannels() {
  const container = el("channels-list");
  container.innerHTML = `<div class="loading-text">Loading channels…</div>`;
  try {
    const res = await state.client.request("channels.status", {});
    const channels = res.channels || res || {};

    const entries = Array.isArray(channels)
      ? channels
      : Object.entries(channels).map(([name, val]) => ({ name, ...val }));

    if (entries.length === 0) {
      container.innerHTML = `<div class="empty-state"><strong>NO CHANNELS</strong>No channels configured</div>`;
      return;
    }

    container.innerHTML = entries.map(ch => {
      const accounts = ch.accounts || (ch.account ? [{ id: ch.account, status: ch.status }] : []);
      const accountsHTML = accounts.length === 0
        ? `<div class="channel-account"><span class="account-id">no accounts</span></div>`
        : accounts.map(a => {
            const st = a.status || "unknown";
            const pill = st === "ok" || st === "ready" ? "ok"
              : st === "error" ? "error"
              : st === "syncing" || st === "connecting" ? "syncing"
              : "warn";
            return `
              <div class="channel-account">
                <span class="account-id">${escHtml(a.id || a.accountId || "—")}</span>
                <span class="status-pill ${pill}">${escHtml(st)}</span>
              </div>
            `;
          }).join("");
      return `
        <div class="channel-card">
          <div class="channel-name">${escHtml(ch.name || ch.channel || "?")}</div>
          <div class="channel-accounts">${accountsHTML}</div>
        </div>
      `;
    }).join("");
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}


// ─────────────────────────────────────────────
// 9. CRON
// ─────────────────────────────────────────────

async function loadCron() {
  const container = el("cron-list");
  container.innerHTML = `<div class="loading-text">Loading cron jobs…</div>`;
  try {
    const res = await state.client.request("cron.list", {});
    const jobs = res.jobs || res || [];
    state.cron = jobs;

    if (jobs.length === 0) {
      container.innerHTML = `<div class="empty-state"><strong>NO CRON JOBS</strong>Schedule recurring tasks with + Add Job</div>`;
      return;
    }

    container.innerHTML = jobs.map(j => `
      <div class="cron-row">
        <div class="cron-enabled ${j.enabled !== false ? "on" : "off"}"></div>
        <div class="cron-name">${escHtml(j.name || j.id || "Unnamed")}</div>
        <div class="cron-schedule">${escHtml(j.schedule || "—")}</div>
        <div class="cron-agent">${escHtml(j.agentId ? `agent: ${j.agentId}` : "")}</div>
        <div class="cron-actions">
          <button class="btn-ghost sm" onclick="runCronNow('${escHtml(j.id)}', '${escHtml(j.name || j.id)}')">▶ Run</button>
          <button class="btn-danger sm" onclick="confirmDeleteCron('${escHtml(j.id)}', '${escHtml(j.name || j.id)}')">✕</button>
        </div>
      </div>
    `).join("");
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}

async function runCronNow(cronId, name) {
  try {
    await state.client.request("cron.run", { id: cronId });
    toast(`Cron job "${name}" triggered`, "success");
  } catch (e) {
    toast("Run failed: " + e.message, "error");
  }
}

function confirmDeleteCron(cronId, name) {
  const close = showModal(
    "Remove Cron Job",
    `<p style="color:var(--text-muted)">Remove cron job <strong style="color:var(--text)">${escHtml(name)}</strong>?</p>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-danger sm" id="m-delete">Remove</button>`,
    null
  );
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-delete", el("modal")).onclick = async () => {
    try {
      await state.client.request("cron.remove", { id: cronId });
      toast(`Cron job removed`, "success");
      close();
      loadCron();
    } catch (e) { toast("Remove failed: " + e.message, "error"); }
  };
}

function openAddCron() {
  const close = showModal(
    "Add Cron Job",
    `<div class="modal-form">
      <div class="form-group"><label>Name</label><input id="cj-name" type="text" placeholder="Daily briefing"/></div>
      <div class="form-group"><label>Schedule <span class="opt">(cron expression)</span></label><input id="cj-schedule" type="text" placeholder="0 9 * * *"/></div>
      <div class="form-group"><label>Message</label><textarea id="cj-message" style="height:80px" placeholder="Your daily summary…"></textarea></div>
      <div class="form-group"><label>Agent ID <span class="opt">(optional)</span></label><input id="cj-agent" type="text" placeholder="default"/></div>
    </div>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-primary sm" id="m-add">Add</button>`,
    null
  );
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-add", el("modal")).onclick = async () => {
    const params = {
      name: el("cj-name").value.trim(),
      schedule: el("cj-schedule").value.trim(),
      message: el("cj-message").value.trim(),
    };
    const agent = el("cj-agent").value.trim();
    if (agent) params.agentId = agent;
    if (!params.name || !params.schedule || !params.message) {
      toast("Name, schedule and message required", "error");
      return;
    }
    try {
      await state.client.request("cron.add", params);
      toast(`Cron job "${params.name}" added`, "success");
      close();
      loadCron();
    } catch (e) { toast("Add failed: " + e.message, "error"); }
  };
}


// ─────────────────────────────────────────────
// 10. MODELS
// ─────────────────────────────────────────────

async function loadModels() {
  const container = el("models-list");
  container.innerHTML = `<div class="loading-text">Loading models…</div>`;
  try {
    const res = await state.client.request("models.list", {});
    const models = res.models || res || [];
    state.models = models;

    if (models.length === 0) {
      container.innerHTML = `<div class="empty-state"><strong>NO MODELS</strong>No models available</div>`;
      return;
    }

    const search = el("models-search");
    const render = (filter) => {
      const filtered = filter
        ? models.filter(m => m.id.toLowerCase().includes(filter) || m.provider?.toLowerCase().includes(filter) || m.name?.toLowerCase().includes(filter))
        : models;
      container.innerHTML = filtered.map(m => `
        <div class="model-card">
          <div class="model-id">${escHtml(m.name || m.id)}</div>
          <div class="model-provider">${escHtml(m.provider || "")}</div>
          <div class="model-meta">
            ${m.contextWindow ? `<span class="model-chip">${(m.contextWindow/1000).toFixed(0)}K ctx</span>` : ""}
            ${m.reasoning ? `<span class="model-chip reasoning">reasoning</span>` : ""}
            <span class="model-chip">${escHtml(m.id)}</span>
          </div>
        </div>
      `).join("") || `<div class="empty-state"><strong>NO MATCH</strong></div>`;
    };
    render("");
    search.oninput = (e) => render(e.target.value.trim().toLowerCase());
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}


// ─────────────────────────────────────────────
// 11. CONFIG
// ─────────────────────────────────────────────

async function loadConfig() {
  try {
    const res = await state.client.request("config.get", {});
    state.config = res;
    const cfg = res.config || res;

    el("config-editor").value = typeof cfg === "string"
      ? cfg
      : JSON.stringify(cfg, null, 2);

    if (state.snapshot) {
      el("cfg-path").textContent    = state.snapshot.configPath || "—";
      el("cfg-state").textContent   = state.snapshot.stateDir || "—";
      el("cfg-version").textContent = state.snapshot.stateVersion
        ? `p${state.snapshot.stateVersion.presence} h${state.snapshot.stateVersion.health}`
        : "—";
    }
  } catch (e) {
    toast("Config load error: " + e.message, "error");
  }
}

async function saveConfig() {
  try {
    const raw = el("config-editor").value.trim();
    let parsed;
    try { parsed = JSON.parse(raw); } catch (e) { toast("Invalid JSON: " + e.message, "error"); return; }
    await state.client.request("config.set", { config: parsed });
    toast("Config saved", "success");
  } catch (e) {
    toast("Save failed: " + e.message, "error");
  }
}


// ─────────────────────────────────────────────
// 12. LOGS
// ─────────────────────────────────────────────

function loadLogs() {
  el("logs-output").innerHTML = "";
  state.logLines = [];
  state.logCursor = 0;
  pollLogs();
}

async function pollLogs() {
  if (!state.client?.connected) return;
  try {
    const res = await state.client.request("logs.tail", {
      cursor: state.logCursor,
      limit: 200,
    });
    if (res.reset) {
      state.logCursor = 0;
      el("logs-output").innerHTML = "";
      state.logLines = [];
    }
    const lines = res.lines || [];
    state.logCursor = res.cursor || state.logCursor;

    if (lines.length > 0) {
      const frag = document.createDocumentFragment();
      for (const line of lines) {
        const div = document.createElement("div");
        div.className = "log-line";
        div.innerHTML = parseLogLine(line);
        frag.appendChild(div);
      }
      el("logs-output").appendChild(frag);
      state.logLines.push(...lines);

      if (state.logFollowing) {
        el("logs-output").scrollTop = el("logs-output").scrollHeight;
      }
    }
  } catch {
    // Gateway might not support logs in this mode — fail silently
  }
  if (!logPollInterval) {
    logPollInterval = setInterval(() => {
      const logsView = document.getElementById("view-logs");
      if (logsView && !logsView.classList.contains("hidden") && state.client?.connected) {
        pollLogs();
      }
    }, 2000);
  }
}

function parseLogLine(line) {
  // Try to extract timestamp + level + message
  const m = line.match(/^(\S+)\s+(\w+)\s+(.*)/s);
  if (m) {
    const [, ts, level, msg] = m;
    const lv = level.toLowerCase();
    return `<span class="log-ts">${escHtml(ts)}</span><span class="log-level ${lv}">${escHtml(level)}</span><span class="log-msg">${escHtml(msg)}</span>`;
  }
  return `<span class="log-msg">${escHtml(line)}</span>`;
}


// ─────────────────────────────────────────────
// 13. NODES
// ─────────────────────────────────────────────

async function loadNodes() {
  const container = el("nodes-list");
  container.innerHTML = `<div class="loading-text">Loading nodes…</div>`;
  try {
    const res = await state.client.request("nodes.list", {});
    const nodes = res.nodes || res || [];
    if (nodes.length === 0) {
      container.innerHTML = `<div class="empty-state"><strong>NO NODES</strong>No remote nodes paired</div>`;
      return;
    }
    container.innerHTML = nodes.map(n => `
      <div class="node-card">
        <div class="node-name">${escHtml(n.name || n.id || "Unknown Node")}</div>
        <div class="node-id">${escHtml(n.id || "")}</div>
        <div class="node-meta">
          ${n.platform ? `<span>Platform: ${escHtml(n.platform)}</span>` : ""}
          ${n.version  ? `<span>Version: ${escHtml(n.version)}</span>` : ""}
          ${n.role     ? `<span>Role: ${escHtml(n.role)}</span>` : ""}
        </div>
      </div>
    `).join("");
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><strong>UNAVAILABLE</strong>${escHtml(e.message)}</div>`;
  }
}


// ─────────────────────────────────────────────
// 14. SESSION SEARCH
// ─────────────────────────────────────────────

function initSessionSearch() {
  const inp = el("sessions-search");
  inp.addEventListener("input", () => {
    const q = inp.value.trim().toLowerCase();
    const filtered = state.sessions.filter(s =>
      !q ||
      (s.key || "").toLowerCase().includes(q) ||
      (s.agentId || "").toLowerCase().includes(q) ||
      (s.derivedTitle || "").toLowerCase().includes(q) ||
      (s.label || "").toLowerCase().includes(q)
    );
    renderSessions(filtered);
  });
}


// ─────────────────────────────────────────────
// 15. EVENT HANDLER
// ─────────────────────────────────────────────

function handleGatewayEvent(frame) {
  // Handle snapshot push events
  if (frame.event === "snapshot" || frame.event === "tick") {
    if (frame.data?.uptimeMs != null) {
      state.snapshot = { ...state.snapshot, ...frame.data };
    }
  }
}


// ─────────────────────────────────────────────
// 16. CONNECT FLOW
// ─────────────────────────────────────────────

async function doConnect() {
  const url      = el("inp-url").value.trim();
  const token    = el("inp-token").value.trim();
  const password = el("inp-password").value.trim();

  if (!url) { showConnectError("Gateway URL is required"); return; }

  el("btn-connect").disabled = true;
  el("btn-connect").textContent = "Connecting…";
  hideConnectError();

  const client = new GatewayClient({
    url,
    token:    token || undefined,
    password: password || undefined,
    onEvent:  handleGatewayEvent,
    onConnect: (hello) => {
      setStatus("connected", `connected`);
      toast("Connected to gateway", "success");
    },
    onDisconnect: (code, reason) => {
      setStatus("error", "disconnected");
      toast(`Disconnected: ${reason || code}`, "error");
    },
    onError: () => {},
  });

  try {
    await client.connect();
    state.client = client;

    // Persist settings
    localStorage.setItem("mc-url", url);
    if (token) localStorage.setItem("mc-token", token);

    // Show shell
    el("connect-overlay").classList.remove("active");
    el("shell").classList.remove("hidden");

    setStatus("connected", url.replace(/^ws(s?):\/\//, ""));
    el("gateway-info").textContent = url;

    // Boot: load agents silently for overview
    await loadAgentsSummary().catch(() => {});
    navigate("overview");

  } catch (e) {
    el("btn-connect").disabled = false;
    el("btn-connect").textContent = "Connect";
    showConnectError(e.message || "Connection failed");
  }
}

function doDisconnect() {
  if (state.client) {
    state.client.disconnect();
    state.client = null;
  }
  clearInterval(logPollInterval);
  logPollInterval = null;
  el("shell").classList.add("hidden");
  el("connect-overlay").classList.add("active");
  el("btn-connect").disabled = false;
  el("btn-connect").textContent = "Connect";
  setStatus("connecting", "Disconnected");
}

function showConnectError(msg) {
  const e = el("connect-error");
  e.textContent = msg;
  e.classList.remove("hidden");
}
function hideConnectError() {
  el("connect-error").classList.add("hidden");
}


// ─────────────────────────────────────────────
// 17. INIT
// ─────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  // Restore saved settings
  const savedUrl   = localStorage.getItem("mc-url");
  const savedToken = localStorage.getItem("mc-token");
  if (savedUrl)   el("inp-url").value   = savedUrl;
  if (savedToken) el("inp-token").value = savedToken;

  // Connect button
  el("btn-connect").addEventListener("click", doConnect);
  el("inp-password").addEventListener("keydown", e => { if (e.key === "Enter") doConnect(); });
  el("inp-token").addEventListener("keydown",    e => { if (e.key === "Enter") doConnect(); });
  el("inp-url").addEventListener("keydown",      e => { if (e.key === "Enter") doConnect(); });

  // Disconnect
  el("btn-disconnect").addEventListener("click", doDisconnect);

  // Nav
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => navigate(btn.dataset.view));
  });

  // Create agent
  el("btn-create-agent").addEventListener("click", openCreateAgent);

  // Add cron
  el("btn-add-cron").addEventListener("click", openAddCron);

  // Save config
  el("btn-save-config").addEventListener("click", saveConfig);

  // Clear logs
  el("btn-clear-logs").addEventListener("click", () => {
    el("logs-output").innerHTML = "";
    state.logLines = [];
  });

  // Logs follow
  el("logs-follow").addEventListener("change", e => {
    state.logFollowing = e.target.checked;
    if (state.logFollowing) {
      el("logs-output").scrollTop = el("logs-output").scrollHeight;
    }
  });

  // Session search
  initSessionSearch();

  // Expose globals for inline onclick handlers
  window.openAgentEdit         = openAgentEdit;
  window.openAgentFiles        = openAgentFiles;
  window.openFileEdit          = openFileEdit;
  window.confirmDeleteAgent    = confirmDeleteAgent;
  window.openSessionDetail     = openSessionDetail;
  window.confirmDeleteSession  = confirmDeleteSession;
  window.runCronNow            = runCronNow;
  window.confirmDeleteCron     = confirmDeleteCron;
});
