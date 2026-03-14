/**
 * OpenClaw Mission Control — mc.js
 * Full operational control plane. Direct WS to OpenClaw gateway.
 *
 * Views: Overview · Agents · Sessions · Channels · Cron · Models
 *        Config · Logs · Nodes · Exec Approvals · Skills · Devices · Usage
 */
"use strict";

// ─────────────────────────────────────────────────────────────────
// 1. GATEWAY CLIENT
// ─────────────────────────────────────────────────────────────────

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
    this.pending = new Map();
    this.seq = 0;
    this.connected = false;
    this.helloData = null;
    this.serverFeatures = null;
  }

  connect() {
    return new Promise((resolve, reject) => {
      try { this.ws = new WebSocket(this.url); }
      catch (e) { reject(e); return; }

      this.ws.onopen = () => {
        const id = this._nextId();
        this.pending.set(id, { resolve: (hello) => {
          this.connected = true;
          this.helloData = hello;
          this.serverFeatures = hello?.features?.methods || [];
          this.onConnect(hello);
          resolve(hello);
        }, reject, isConnect: true });
        this.ws.send(JSON.stringify({
          type: "request", id, command: "connect",
          params: {
            minProtocol: 4, maxProtocol: 9,
            client: { id: "mission-control", displayName: "Mission Control",
                      version: "1.0.0", platform: "web", mode: "control" },
            auth: { token: this.token || undefined, password: this.password || undefined },
          },
        }));
      };

      this.ws.onmessage = (evt) => {
        let frame;
        try { frame = JSON.parse(evt.data); } catch { return; }
        this._handleFrame(frame);
      };

      this.ws.onclose = (evt) => {
        this.connected = false;
        for (const [, p] of this.pending) p.reject(new Error("WebSocket closed"));
        this.pending.clear();
        this.onDisconnect(evt.code, evt.reason || "closed");
      };

      this.ws.onerror = (err) => { this.onError(err); reject(err); };
    });
  }

  disconnect() {
    if (this.ws) { this.ws.onclose = null; this.ws.close(); this.ws = null; }
    this.connected = false;
  }

  request(command, params = {}) {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error("Not connected")); return;
      }
      const id = this._nextId();
      this.pending.set(id, { resolve, reject, isConnect: false });
      this.ws.send(JSON.stringify({ type: "request", id, command, params }));
    });
  }

  supports(method) {
    if (!this.serverFeatures) return true; // assume yes if unknown
    return this.serverFeatures.includes(method);
  }

  _nextId() { return `mc-${Date.now()}-${++this.seq}`; }

  _handleFrame(frame) {
    if (frame.type === "response") {
      const p = this.pending.get(frame.id);
      if (!p) return;
      this.pending.delete(frame.id);
      if (frame.error) {
        const e = Object.assign(new Error(frame.error.message || "Gateway error"),
                                { code: frame.error.code });
        p.reject(e);
      } else {
        p.resolve(frame.result);
      }
    } else if (frame.type === "event") {
      this.onEvent(frame);
    }
  }
}


// ─────────────────────────────────────────────────────────────────
// 2. APP STATE
// ─────────────────────────────────────────────────────────────────

const state = {
  client: null,
  snapshot: null,
  agents: [],
  defaultAgentId: null,
  sessions: [],
  channels: {},
  cron: [],
  models: [],
  nodes: [],
  config: null,
  logLines: [],
  logCursor: 0,
  logFollowing: true,
  pendingApprovals: [],    // live approval requests received via events
  approvalsPolicy: null,
  skills: [],
  devicePairRequests: [],
  devices: [],
};

let logPollInterval = null;
let approvalPollInterval = null;


// ─────────────────────────────────────────────────────────────────
// 3. DOM HELPERS
// ─────────────────────────────────────────────────────────────────

const el = (id) => document.getElementById(id);
const qs = (sel, root = document) => root.querySelector(sel);

function toast(msg, type = "info", ms = 3500) {
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.textContent = msg;
  el("toast-container").appendChild(t);
  setTimeout(() => t.remove(), ms);
}

function setStatus(cls, label) {
  el("status-dot").className = `status-dot ${cls}`;
  el("status-label").textContent = label;
}

function showModal(title, bodyHTML, footerHTML) {
  el("modal-title").textContent = title;
  el("modal-body").innerHTML = bodyHTML;
  el("modal-footer").innerHTML = footerHTML;
  el("modal-backdrop").classList.remove("hidden");
  const close = () => el("modal-backdrop").classList.add("hidden");
  el("modal-close").onclick = close;
  el("modal-backdrop").onclick = (e) => { if (e.target === el("modal-backdrop")) close(); };
  return close;
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

function fmtTokens(n) {
  if (!n) return "0";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function fmtCost(cents) {
  if (!cents) return "$0.00";
  return "$" + (cents / 100).toFixed(4);
}

function fmtTs(ms) {
  if (!ms) return "—";
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmtDate(ms) {
  if (!ms) return "—";
  return new Date(ms).toLocaleDateString([], { month: "short", day: "numeric" });
}

function escHtml(s) {
  return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;")
                         .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}


// ─────────────────────────────────────────────────────────────────
// 4. NAVIGATION
// ─────────────────────────────────────────────────────────────────

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
  approvals: loadApprovals,
  skills:    loadSkills,
  devices:   loadDevices,
  usage:     loadUsage,
};

function navigate(view) {
  document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".view").forEach(v => v.classList.add("hidden"));
  const btn = document.querySelector(`.nav-item[data-view="${view}"]`);
  if (btn) btn.classList.add("active");
  const viewEl = el(`view-${view}`);
  if (viewEl) viewEl.classList.remove("hidden");
  if (viewLoaders[view] && state.client?.connected) viewLoaders[view]();
}


// ─────────────────────────────────────────────────────────────────
// 5. OVERVIEW
// ─────────────────────────────────────────────────────────────────

async function loadOverview() {
  try {
    const snap = await state.client.request("snapshot", {});
    state.snapshot = snap;

    qs(".stat-value", el("stat-agents")).textContent   = state.agents.length || "—";
    qs(".stat-value", el("stat-sessions")).textContent = state.sessions.length || "—";
    qs(".stat-value", el("stat-clients")).textContent  = (snap.presence || []).length;
    qs(".stat-value", el("stat-uptime")).textContent   = snap.uptimeMs ? fmtUptime(snap.uptimeMs) : "—";
    el("uptime-badge").textContent = snap.uptimeMs ? `up ${fmtUptime(snap.uptimeMs)}` : "—";

    const presence = snap.presence || [];
    el("presence-list").innerHTML = presence.length === 0
      ? `<div class="empty-state"><strong>NO CLIENTS</strong>None connected</div>`
      : presence.map(p => `
          <div class="presence-entry">
            <span class="pe-mode">${escHtml(p.mode || "?")}</span>
            <span class="pe-name">${escHtml(p.host || p.ip || "unknown")}</span>
            <span class="pe-platform">${escHtml(p.platform || "")}</span>
          </div>`).join("");

    await loadAgentsSummary();
    el("agents-overview-list").innerHTML = state.agents.length === 0
      ? `<div class="empty-state"><strong>NO AGENTS</strong>Create one in the Agents view</div>`
      : state.agents.map(a => `
          <div class="presence-entry">
            <span class="pe-mode">${escHtml(a.identity?.emoji || "🤖")}</span>
            <span class="pe-name">${escHtml(a.identity?.name || a.name || a.id)}</span>
            <span class="pe-platform">${escHtml(a.id)}</span>
          </div>`).join("");

    if (snap.configPath)
      el("gateway-info").innerHTML = [
        snap.configPath ? `cfg: ${snap.configPath.split("/").slice(-3).join("/")}` : "",
        snap.stateDir   ? `state: ${snap.stateDir.split("/").slice(-2).join("/")}` : "",
      ].filter(Boolean).join("<br>");
  } catch (e) {
    toast("Overview error: " + e.message, "error");
  }
}


// ─────────────────────────────────────────────────────────────────
// 6. AGENTS
// ─────────────────────────────────────────────────────────────────

async function loadAgentsSummary() {
  try {
    const res = await state.client.request("agents.list", {});
    state.agents = res.agents || [];
    state.defaultAgentId = res.defaultId;
    return res;
  } catch { return null; }
}

async function loadAgents() {
  const container = el("agents-list");
  container.innerHTML = `<div class="loading-text">Loading agents…</div>`;
  try {
    const res = await state.client.request("agents.list", {});
    state.agents = res.agents || [];
    state.defaultAgentId = res.defaultId;

    if (!state.agents.length) {
      container.innerHTML = `<div class="empty-state"><strong>NO AGENTS</strong>Click + New Agent to create one</div>`;
      return;
    }
    container.innerHTML = state.agents.map(a => {
      const name    = a.identity?.name || a.name || a.id;
      const emoji   = a.identity?.emoji || "🤖";
      const isDef   = a.id === res.defaultId;
      return `
        <div class="agent-card ${isDef ? "is-default" : ""}">
          <div class="agent-card-header">
            <div class="agent-avatar">${escHtml(emoji)}</div>
            <div>
              <div class="agent-name">${escHtml(name)}</div>
              <div class="agent-id">${escHtml(a.id)}</div>
            </div>
          </div>
          <div class="agent-badges">
            ${isDef ? `<span class="chip chip-default">DEFAULT</span>` : ""}
          </div>
          <div class="agent-card-actions">
            <button class="btn-ghost sm" onclick="openAgentEdit('${escHtml(a.id)}')">Edit</button>
            <button class="btn-ghost sm" onclick="openAgentFiles('${escHtml(a.id)}')">Files</button>
            <button class="btn-ghost sm" onclick="openAgentPolicy('${escHtml(a.id)}')">Policy</button>
            <button class="btn-danger sm" onclick="confirmDeleteAgent('${escHtml(a.id)}','${escHtml(name)}')">Delete</button>
          </div>
        </div>`;
    }).join("");
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}

function openCreateAgent() {
  const close = showModal("Create Agent",
    `<div class="modal-form">
       <div class="form-group"><label>Name</label><input id="na-name" type="text" placeholder="My Agent"/></div>
       <div class="form-group"><label>Workspace</label><input id="na-workspace" type="text" placeholder="~/openclaw/workspaces/my-agent"/></div>
       <div class="form-group"><label>Emoji <span class="opt">(optional)</span></label><input id="na-emoji" type="text" placeholder="🤖"/></div>
     </div>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-primary sm" id="m-create">Create</button>`);
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-create", el("modal")).onclick = async () => {
    const name = el("na-name").value.trim();
    const workspace = el("na-workspace").value.trim();
    const emoji = el("na-emoji").value.trim();
    if (!name || !workspace) { toast("Name and workspace required", "error"); return; }
    try {
      const res = await state.client.request("agents.create", { name, workspace, emoji: emoji || undefined });
      toast(`Agent "${res.name}" created`, "success");
      close(); loadAgents();
    } catch (e) { toast("Create failed: " + e.message, "error"); }
  };
}

async function openAgentEdit(agentId) {
  const a = state.agents.find(x => x.id === agentId) || {};
  const close = showModal(`Edit Agent: ${agentId}`,
    `<div class="modal-form">
       <div class="form-group"><label>Name</label><input id="ea-name" type="text" value="${escHtml(a.identity?.name || a.name || "")}"/></div>
       <div class="form-group"><label>Emoji</label><input id="ea-emoji" type="text" value="${escHtml(a.identity?.emoji || "")}"/></div>
       <div class="form-group"><label>Model <span class="opt">(leave blank to keep)</span></label><input id="ea-model" type="text" placeholder="anthropic/claude-sonnet-4-20250514"/></div>
     </div>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-primary sm" id="m-save">Save</button>`);
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
      close(); loadAgents();
    } catch (err) { toast("Update failed: " + err.message, "error"); }
  };
}

async function openAgentFiles(agentId) {
  try {
    const res = await state.client.request("agents.files.list", { agentId });
    const files = res.files || [];
    const close = showModal(`Files: ${agentId}`,
      `<div style="margin-bottom:10px;font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">${escHtml(res.workspace)}</div>
       <div>
       ${files.length === 0
         ? `<div class="empty-state"><strong>NO FILES</strong></div>`
         : files.map(f => `
             <div class="presence-entry" style="cursor:pointer" onclick="openFileEdit('${escHtml(agentId)}','${escHtml(f.name)}')">
               <span class="pe-mode" style="${f.missing ? "background:var(--error-dim);color:var(--error)" : ""}">${f.missing ? "MISSING" : "FILE"}</span>
               <span class="pe-name">${escHtml(f.name)}</span>
               <span class="pe-platform">${f.size != null ? (f.size/1024).toFixed(1)+"KB" : ""}</span>
             </div>`).join("")}
       </div>`,
      `<button class="btn-ghost sm" id="m-close">Close</button>`);
    qs("#m-close", el("modal")).onclick = close;
  } catch (e) { toast("Files error: " + e.message, "error"); }
}

async function openFileEdit(agentId, fileName) {
  try {
    const res = await state.client.request("agents.files.get", { agentId, name: fileName });
    const close = showModal(`${agentId} / ${fileName}`,
      `<textarea id="fe-content" class="config-editor" style="height:340px">${escHtml(res.file?.content || "")}</textarea>`,
      `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
       <button class="btn-primary sm" id="m-save">Save</button>`);
    qs("#m-cancel", el("modal")).onclick = close;
    qs("#m-save", el("modal")).onclick = async () => {
      try {
        await state.client.request("agents.files.set", { agentId, name: fileName, content: el("fe-content").value });
        toast(`Saved ${fileName}`, "success"); close();
      } catch (e) { toast("Save failed: " + e.message, "error"); }
    };
  } catch (e) { toast("File error: " + e.message, "error"); }
}

async function openAgentPolicy(agentId) {
  // Exec approvals policy for this specific agent
  try {
    const res = await state.client.request("exec.approvals.get", {});
    const policy = res?.file || {};
    const agentPolicy = policy.agents?.[agentId] || {};
    const allowlist = agentPolicy.allowlist || [];
    const securityOpts = ["allow", "deny", "ask", "block"];
    const currentSecurity = agentPolicy.security || policy.defaults?.security || "ask";

    const close = showModal(`Policy: ${agentId}`,
      `<div class="modal-form">
         <div class="form-group">
           <label>Exec Security</label>
           <select id="ap-security">
             ${securityOpts.map(o => `<option value="${o}" ${o === currentSecurity ? "selected" : ""}>${o}</option>`).join("")}
           </select>
         </div>
         <div class="form-group">
           <label>Allowlist <span class="opt">(one pattern per line)</span></label>
           <textarea id="ap-allowlist" style="height:120px;font-family:var(--font-mono);font-size:12px">${allowlist.map(e => e.pattern).join("\n")}</textarea>
         </div>
       </div>`,
      `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
       <button class="btn-primary sm" id="m-save">Save</button>`);
    qs("#m-cancel", el("modal")).onclick = close;
    qs("#m-save", el("modal")).onclick = async () => {
      const security = el("ap-security").value;
      const patterns = el("ap-allowlist").value.split("\n").map(l => l.trim()).filter(Boolean);
      const newPolicy = {
        ...policy,
        agents: {
          ...(policy.agents || {}),
          [agentId]: {
            ...agentPolicy,
            security,
            allowlist: patterns.map(p => ({ pattern: p })),
          },
        },
      };
      try {
        await state.client.request("exec.approvals.set", { file: { version: 1, ...newPolicy }, baseHash: res.hash });
        toast(`Policy updated for ${agentId}`, "success"); close();
      } catch (e) { toast("Save failed: " + e.message, "error"); }
    };
  } catch (e) { toast("Policy load error: " + e.message, "error"); }
}

function confirmDeleteAgent(agentId, name) {
  const close = showModal("Delete Agent",
    `<p style="color:var(--text-muted)">Delete <strong style="color:var(--text)">${escHtml(name)}</strong> (<code style="font-family:var(--font-mono);color:var(--error)">${escHtml(agentId)}</code>)?</p>
     <p style="margin-top:10px;font-size:12px;color:var(--text-dim)">Config removed. Transcripts preserved.</p>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-danger sm" id="m-delete">Delete</button>`);
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-delete", el("modal")).onclick = async () => {
    try {
      await state.client.request("agents.delete", { agentId, deleteFiles: false });
      toast(`Deleted ${agentId}`, "success"); close(); loadAgents();
    } catch (e) { toast("Delete failed: " + e.message, "error"); }
  };
}


// ─────────────────────────────────────────────────────────────────
// 7. SESSIONS
// ─────────────────────────────────────────────────────────────────

async function loadSessions() {
  el("sessions-list").innerHTML = `<div class="loading-text">Loading sessions…</div>`;
  try {
    const res = await state.client.request("sessions.list", {
      limit: 200, includeDerivedTitles: true,
    });
    state.sessions = res.sessions || res || [];
    renderSessions(state.sessions);
  } catch (e) {
    el("sessions-list").innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}

function renderSessions(sessions) {
  if (!sessions?.length) {
    el("sessions-list").innerHTML = `<div class="empty-state"><strong>NO SESSIONS</strong>Sessions appear when agents have conversations</div>`;
    return;
  }
  el("sessions-list").innerHTML = sessions.map(s => {
    const title = s.derivedTitle || s.label || s.key?.split(":").pop() || s.key || "—";
    return `
      <div class="session-row" onclick="openSessionDetail('${escHtml(s.key)}')">
        <span class="session-key">${escHtml(s.key || "")}</span>
        <span class="session-agent">${escHtml(s.agentId || "—")}</span>
        <span class="session-title">${escHtml(title)}</span>
        <span class="session-ts">${fmtTs(s.updatedAtMs || s.createdAtMs)}</span>
        <span class="session-actions">
          <button class="btn-ghost sm" onclick="event.stopPropagation();confirmDeleteSession('${escHtml(s.key)}')">✕</button>
        </span>
      </div>`;
  }).join("");
}

async function openSessionDetail(sessionKey) {
  try {
    const res = await state.client.request("sessions.preview", { keys: [sessionKey], maxChars: 3000 });
    const preview = (res.previews || [])[0] || {};
    const close = showModal(`Session: ${sessionKey}`,
      `<div style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);
                   white-space:pre-wrap;max-height:400px;overflow-y:auto;
                   background:var(--bg);padding:12px;border-radius:4px">${escHtml(preview.content || "(empty)")}</div>`,
      `<button class="btn-ghost sm" id="m-close">Close</button>
       <button class="btn-ghost sm" id="m-compact">Compact</button>
       <button class="btn-danger sm" id="m-reset">Reset</button>`);
    qs("#m-close", el("modal")).onclick = close;
    qs("#m-compact", el("modal")).onclick = async () => {
      try {
        await state.client.request("sessions.compact", { key: sessionKey });
        toast("Session compacted", "success"); close();
      } catch (e) { toast("Compact failed: " + e.message, "error"); }
    };
    qs("#m-reset", el("modal")).onclick = async () => {
      try {
        await state.client.request("sessions.reset", { key: sessionKey });
        toast("Session reset", "success"); close(); loadSessions();
      } catch (e) { toast("Reset failed: " + e.message, "error"); }
    };
  } catch (e) { toast("Session error: " + e.message, "error"); }
}

function confirmDeleteSession(key) {
  const close = showModal("Delete Session",
    `<p style="color:var(--text-muted)">Delete session <code style="font-family:var(--font-mono);color:var(--error)">${escHtml(key)}</code>?</p>
     <label style="display:flex;align-items:center;gap:8px;margin-top:12px;font-size:12px;cursor:pointer">
       <input type="checkbox" id="del-transcript"> Delete transcript file
     </label>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-danger sm" id="m-delete">Delete</button>`);
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-delete", el("modal")).onclick = async () => {
    try {
      await state.client.request("sessions.delete", { key, deleteTranscript: el("del-transcript")?.checked || false });
      toast("Session deleted", "success"); close(); loadSessions();
    } catch (e) { toast("Delete failed: " + e.message, "error"); }
  };
}


// ─────────────────────────────────────────────────────────────────
// 8. CHANNELS
// ─────────────────────────────────────────────────────────────────

async function loadChannels() {
  el("channels-list").innerHTML = `<div class="loading-text">Loading channels…</div>`;
  try {
    const res = await state.client.request("channels.status", {});
    const raw = res.channels || res || {};
    const entries = Array.isArray(raw)
      ? raw
      : Object.entries(raw).map(([name, val]) => ({ name, ...(typeof val === "object" ? val : {}) }));

    if (!entries.length) {
      el("channels-list").innerHTML = `<div class="empty-state"><strong>NO CHANNELS</strong>No channels configured</div>`;
      return;
    }
    el("channels-list").innerHTML = entries.map(ch => {
      const accounts = ch.accounts || (ch.account ? [{ id: ch.account, status: ch.status }] : []);
      return `
        <div class="channel-card">
          <div class="channel-name">${escHtml(ch.name || ch.channel || "?")}</div>
          <div class="channel-accounts">
          ${accounts.length === 0
            ? `<div class="channel-account"><span class="account-id">no accounts</span></div>`
            : accounts.map(a => {
                const st = a.status || "unknown";
                const pill = st === "ok" || st === "ready" ? "ok"
                           : st === "error" ? "error"
                           : st === "syncing" || st === "connecting" ? "syncing" : "warn";
                return `<div class="channel-account">
                  <span class="account-id">${escHtml(a.id || a.accountId || "—")}</span>
                  <span class="status-pill ${pill}">${escHtml(st)}</span>
                </div>`;
              }).join("")}
          </div>
        </div>`;
    }).join("");
  } catch (e) {
    el("channels-list").innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}


// ─────────────────────────────────────────────────────────────────
// 9. CRON
// ─────────────────────────────────────────────────────────────────

async function loadCron() {
  el("cron-list").innerHTML = `<div class="loading-text">Loading cron jobs…</div>`;
  try {
    const res = await state.client.request("cron.list", {});
    state.cron = res.jobs || res || [];
    if (!state.cron.length) {
      el("cron-list").innerHTML = `<div class="empty-state"><strong>NO CRON JOBS</strong>Click + Add Job to schedule recurring tasks</div>`;
      return;
    }
    el("cron-list").innerHTML = state.cron.map(j => `
      <div class="cron-row">
        <div class="cron-enabled ${j.enabled !== false ? "on" : "off"}"></div>
        <div class="cron-name">${escHtml(j.name || j.id || "Unnamed")}</div>
        <div class="cron-schedule">${escHtml(j.schedule || "—")}</div>
        <div class="cron-agent">${escHtml(j.agentId ? `agent: ${j.agentId}` : "")}</div>
        <div class="cron-actions">
          <button class="btn-ghost sm" onclick="runCronNow('${escHtml(j.id)}','${escHtml(j.name || j.id)}')">▶ Run</button>
          <button class="btn-ghost sm" onclick="editCronJob('${escHtml(j.id)}')">Edit</button>
          <button class="btn-danger sm" onclick="confirmDeleteCron('${escHtml(j.id)}','${escHtml(j.name || j.id)}')">✕</button>
        </div>
      </div>`).join("");
  } catch (e) {
    el("cron-list").innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}

async function runCronNow(id, name) {
  try {
    await state.client.request("cron.run", { id });
    toast(`"${name}" triggered`, "success");
  } catch (e) { toast("Run failed: " + e.message, "error"); }
}

function editCronJob(id) {
  const job = state.cron.find(j => j.id === id);
  if (!job) return;
  const close = showModal(`Edit: ${job.name || id}`,
    `<div class="modal-form">
       <div class="form-group"><label>Name</label><input id="ej-name" type="text" value="${escHtml(job.name || "")}"/></div>
       <div class="form-group"><label>Schedule</label><input id="ej-schedule" type="text" value="${escHtml(job.schedule || "")}"/></div>
       <div class="form-group"><label>Enabled</label>
         <select id="ej-enabled">
           <option value="true" ${job.enabled !== false ? "selected" : ""}>Enabled</option>
           <option value="false" ${job.enabled === false ? "selected" : ""}>Disabled</option>
         </select>
       </div>
     </div>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-primary sm" id="m-save">Save</button>`);
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-save", el("modal")).onclick = async () => {
    try {
      await state.client.request("cron.update", {
        id,
        name: el("ej-name").value.trim() || undefined,
        schedule: el("ej-schedule").value.trim() || undefined,
        enabled: el("ej-enabled").value === "true",
      });
      toast("Cron job updated", "success"); close(); loadCron();
    } catch (e) { toast("Update failed: " + e.message, "error"); }
  };
}

function confirmDeleteCron(id, name) {
  const close = showModal("Remove Cron Job",
    `<p style="color:var(--text-muted)">Remove <strong style="color:var(--text)">${escHtml(name)}</strong>?</p>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-danger sm" id="m-delete">Remove</button>`);
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-delete", el("modal")).onclick = async () => {
    try {
      await state.client.request("cron.remove", { id });
      toast("Job removed", "success"); close(); loadCron();
    } catch (e) { toast("Remove failed: " + e.message, "error"); }
  };
}

function openAddCron() {
  const close = showModal("Add Cron Job",
    `<div class="modal-form">
       <div class="form-group"><label>Name</label><input id="cj-name" type="text" placeholder="Daily briefing"/></div>
       <div class="form-group"><label>Schedule <span class="opt">(cron expression)</span></label><input id="cj-schedule" type="text" placeholder="0 9 * * *"/></div>
       <div class="form-group"><label>Message</label><textarea id="cj-message" style="height:80px" placeholder="Your daily summary…"></textarea></div>
       <div class="form-group"><label>Agent ID <span class="opt">(optional)</span></label><input id="cj-agent" type="text" placeholder="default"/></div>
     </div>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-primary sm" id="m-add">Add</button>`);
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-add", el("modal")).onclick = async () => {
    const name = el("cj-name").value.trim();
    const schedule = el("cj-schedule").value.trim();
    const message = el("cj-message").value.trim();
    const agentId = el("cj-agent").value.trim() || undefined;
    if (!name || !schedule || !message) { toast("Name, schedule, message required", "error"); return; }
    try {
      await state.client.request("cron.add", { name, schedule, message, agentId });
      toast(`"${name}" added`, "success"); close(); loadCron();
    } catch (e) { toast("Add failed: " + e.message, "error"); }
  };
}


// ─────────────────────────────────────────────────────────────────
// 10. MODELS
// ─────────────────────────────────────────────────────────────────

async function loadModels() {
  el("models-list").innerHTML = `<div class="loading-text">Loading models…</div>`;
  try {
    const res = await state.client.request("models.list", {});
    state.models = res.models || res || [];
    const render = (f) => {
      const filtered = f ? state.models.filter(m =>
        (m.id||"").toLowerCase().includes(f) ||
        (m.provider||"").toLowerCase().includes(f) ||
        (m.name||"").toLowerCase().includes(f)) : state.models;
      el("models-list").innerHTML = filtered.map(m => `
        <div class="model-card">
          <div class="model-id">${escHtml(m.name || m.id)}</div>
          <div class="model-provider">${escHtml(m.provider || "")}</div>
          <div class="model-meta">
            ${m.contextWindow ? `<span class="model-chip">${(m.contextWindow/1000).toFixed(0)}K ctx</span>` : ""}
            ${m.reasoning ? `<span class="model-chip reasoning">reasoning</span>` : ""}
            <span class="model-chip">${escHtml(m.id)}</span>
          </div>
        </div>`).join("") || `<div class="empty-state"><strong>NO MATCH</strong></div>`;
    };
    render("");
    el("models-search").oninput = (e) => render(e.target.value.trim().toLowerCase());
  } catch (e) {
    el("models-list").innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}


// ─────────────────────────────────────────────────────────────────
// 11. CONFIG
// ─────────────────────────────────────────────────────────────────

async function loadConfig() {
  try {
    const res = await state.client.request("config.get", {});
    state.config = res;
    const cfg = res.config || res;
    el("config-editor").value = typeof cfg === "string" ? cfg : JSON.stringify(cfg, null, 2);
    if (state.snapshot) {
      el("cfg-path").textContent  = state.snapshot.configPath || "—";
      el("cfg-state").textContent = state.snapshot.stateDir || "—";
      el("cfg-version").textContent = state.snapshot.stateVersion
        ? `p${state.snapshot.stateVersion.presence} h${state.snapshot.stateVersion.health}` : "—";
    }
  } catch (e) { toast("Config load error: " + e.message, "error"); }
}

async function saveConfig() {
  try {
    const raw = el("config-editor").value.trim();
    let parsed;
    try { parsed = JSON.parse(raw); } catch (e) { toast("Invalid JSON: " + e.message, "error"); return; }
    await state.client.request("config.set", { config: parsed });
    toast("Config saved", "success");
  } catch (e) { toast("Save failed: " + e.message, "error"); }
}


// ─────────────────────────────────────────────────────────────────
// 12. LOGS
// ─────────────────────────────────────────────────────────────────

function loadLogs() {
  el("logs-output").innerHTML = "";
  state.logLines = [];
  state.logCursor = 0;
  pollLogs();
  if (!logPollInterval) {
    logPollInterval = setInterval(() => {
      if (!el("view-logs").classList.contains("hidden") && state.client?.connected) pollLogs();
    }, 2000);
  }
}

async function pollLogs() {
  if (!state.client?.connected) return;
  try {
    const res = await state.client.request("logs.tail", { cursor: state.logCursor, limit: 300 });
    if (res.reset) { state.logCursor = 0; el("logs-output").innerHTML = ""; }
    const lines = res.lines || [];
    state.logCursor = res.cursor || state.logCursor;
    if (lines.length) {
      const frag = document.createDocumentFragment();
      for (const line of lines) {
        const d = document.createElement("div");
        d.className = "log-line";
        d.innerHTML = parseLogLine(line);
        frag.appendChild(d);
      }
      el("logs-output").appendChild(frag);
      if (state.logFollowing) el("logs-output").scrollTop = el("logs-output").scrollHeight;
    }
  } catch { /* logs.tail may not be available in all auth modes */ }
}

function parseLogLine(line) {
  const m = line.match(/^(\S+)\s+(\w+)\s+(.*)/s);
  if (m) {
    const [, ts, level, msg] = m;
    return `<span class="log-ts">${escHtml(ts)}</span><span class="log-level ${level.toLowerCase()}">${escHtml(level)}</span><span class="log-msg">${escHtml(msg)}</span>`;
  }
  return `<span class="log-msg">${escHtml(line)}</span>`;
}


// ─────────────────────────────────────────────────────────────────
// 13. NODES
// ─────────────────────────────────────────────────────────────────

async function loadNodes() {
  el("nodes-list").innerHTML = `<div class="loading-text">Loading nodes…</div>`;
  try {
    const res = await state.client.request("nodes.list", {});
    const nodes = res.nodes || res || [];
    if (!nodes.length) {
      el("nodes-list").innerHTML = `<div class="empty-state"><strong>NO NODES</strong>No remote nodes paired</div>`;
      return;
    }
    el("nodes-list").innerHTML = nodes.map(n => `
      <div class="node-card">
        <div class="node-name">${escHtml(n.displayName || n.name || n.id)}</div>
        <div class="node-id">${escHtml(n.id || "")}</div>
        <div class="node-meta">
          ${n.platform ? `<span>Platform: ${escHtml(n.platform)}</span>` : ""}
          ${n.version  ? `<span>Version: ${escHtml(n.version)}</span>`  : ""}
          ${n.role     ? `<span>Role: ${escHtml(n.role)}</span>`         : ""}
        </div>
      </div>`).join("");
  } catch (e) {
    el("nodes-list").innerHTML = `<div class="empty-state"><strong>UNAVAILABLE</strong>${escHtml(e.message)}</div>`;
  }
}


// ─────────────────────────────────────────────────────────────────
// 14. EXEC APPROVALS
// ─────────────────────────────────────────────────────────────────

async function loadApprovals() {
  // Render any live pending approvals from event stream first
  renderApprovalQueue();

  // Load policy
  try {
    const res = await state.client.request("exec.approvals.get", {});
    state.approvalsPolicy = res;
    renderApprovalsPolicy(res);
  } catch (e) {
    el("approvals-policy").innerHTML = `<div class="empty-state"><strong>UNAVAILABLE</strong>${escHtml(e.message)}</div>`;
  }
}

function renderApprovalQueue() {
  const pending = state.pendingApprovals;
  const count = pending.length;

  el("approvals-pending-count").textContent = `${count} pending`;

  // Update nav badge
  const badge = el("approval-badge");
  if (count > 0) {
    badge.textContent = count;
    badge.classList.remove("hidden");
  } else {
    badge.classList.add("hidden");
  }

  if (!count) {
    el("approvals-queue").innerHTML = `<div class="empty-state"><strong>NO PENDING APPROVALS</strong>Exec approval requests will appear here in real-time</div>`;
    return;
  }

  el("approvals-queue").innerHTML = pending.map(req => `
    <div class="approval-card" id="appr-${escHtml(req.id)}">
      <div class="approval-header">
        <span class="approval-badge">PENDING</span>
        ${req.agentId ? `<span style="font-size:12px;color:var(--text-muted)">${escHtml(req.agentId)}</span>` : ""}
        ${req.cwd     ? `<span style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">${escHtml(req.cwd)}</span>` : ""}
        <span class="approval-id">${escHtml(req.id)}</span>
      </div>
      <div class="approval-command">${escHtml(req.command)}</div>
      ${req.host ? `<div class="approval-meta"><span><span class="meta-label">host: </span>${escHtml(req.host)}</span></div>` : ""}
      <div class="approval-actions">
        <button class="btn-approve" onclick="resolveApproval('${escHtml(req.id)}','allow')">✓ Allow Once</button>
        <button class="btn-allow-always" onclick="resolveApproval('${escHtml(req.id)}','allow-pattern')">Allow Always</button>
        <button class="btn-danger sm" onclick="resolveApproval('${escHtml(req.id)}','deny')">✕ Deny</button>
      </div>
    </div>`).join("");
}

async function resolveApproval(id, decision) {
  try {
    await state.client.request("exec.approval.resolve", { id, decision });
    state.pendingApprovals = state.pendingApprovals.filter(r => r.id !== id);
    renderApprovalQueue();
    toast(`Approval ${decision === "deny" ? "denied" : "approved"}`, decision === "deny" ? "error" : "success");
  } catch (e) { toast("Resolve failed: " + e.message, "error"); }
}

function renderApprovalsPolicy(res) {
  const file = res?.file || {};
  const defaults = file.defaults || {};
  const agents = file.agents || {};

  let html = "";

  // Defaults section
  html += `
    <div class="policy-agent-section">
      <div class="policy-agent-label">DEFAULTS</div>
      <div class="allowlist-entry" style="justify-content:space-between">
        <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted)">security: <strong style="color:var(--text)">${escHtml(defaults.security || "ask")}</strong></span>
        <button class="btn-ghost sm" onclick="editDefaultPolicy()">Edit</button>
      </div>
    </div>`;

  // Per-agent sections
  for (const [agentId, agentPolicy] of Object.entries(agents)) {
    const allowlist = agentPolicy.allowlist || [];
    html += `
      <div class="policy-agent-section">
        <div class="policy-agent-label">${escHtml(agentId)}</div>
        ${allowlist.map((e, i) => `
          <div class="allowlist-entry">
            <span class="allowlist-pattern">${escHtml(e.pattern)}</span>
            ${e.lastUsedCommand ? `<span class="allowlist-last">${escHtml(e.lastUsedCommand.slice(0, 30))}</span>` : ""}
            <button class="btn-remove-allow" onclick="removeAllowlistEntry('${escHtml(agentId)}', ${i})">✕</button>
          </div>`).join("")}
        ${allowlist.length === 0 ? `<div style="padding:6px 10px;font-size:11px;color:var(--text-dim)">No allowlist entries</div>` : ""}
      </div>`;
  }

  if (!html) html = `<div class="empty-state"><strong>NO POLICY</strong>Default settings apply</div>`;
  el("approvals-policy").innerHTML = html;
}

function editDefaultPolicy() {
  if (!state.approvalsPolicy) return;
  const file = state.approvalsPolicy.file || {};
  const defaults = file.defaults || {};
  const close = showModal("Default Exec Policy",
    `<div class="modal-form">
       <div class="form-group">
         <label>Security</label>
         <select id="dp-security">
           ${["allow","deny","ask","block"].map(o =>
             `<option value="${o}" ${(defaults.security||"ask") === o ? "selected" : ""}>${o}</option>`
           ).join("")}
         </select>
       </div>
       <div class="form-group">
         <label>Auto-allow Skills</label>
         <select id="dp-autoskills">
           <option value="true"  ${defaults.autoAllowSkills ? "selected" : ""}>Yes</option>
           <option value="false" ${!defaults.autoAllowSkills ? "selected" : ""}>No</option>
         </select>
       </div>
     </div>`,
    `<button class="btn-ghost sm" id="m-cancel">Cancel</button>
     <button class="btn-primary sm" id="m-save">Save</button>`);
  qs("#m-cancel", el("modal")).onclick = close;
  qs("#m-save", el("modal")).onclick = async () => {
    const newFile = {
      ...file,
      version: 1,
      defaults: {
        ...defaults,
        security: el("dp-security").value,
        autoAllowSkills: el("dp-autoskills").value === "true",
      },
    };
    try {
      await state.client.request("exec.approvals.set", { file: newFile, baseHash: state.approvalsPolicy.hash });
      toast("Default policy saved", "success");
      close();
      loadApprovals();
    } catch (e) { toast("Save failed: " + e.message, "error"); }
  };
}

async function removeAllowlistEntry(agentId, index) {
  if (!state.approvalsPolicy) return;
  const file = state.approvalsPolicy.file || {};
  const agentPolicy = file.agents?.[agentId] || {};
  const allowlist = [...(agentPolicy.allowlist || [])];
  allowlist.splice(index, 1);
  const newFile = {
    ...file,
    version: 1,
    agents: { ...(file.agents || {}), [agentId]: { ...agentPolicy, allowlist } },
  };
  try {
    await state.client.request("exec.approvals.set", { file: newFile, baseHash: state.approvalsPolicy.hash });
    toast("Entry removed", "success");
    loadApprovals();
  } catch (e) { toast("Remove failed: " + e.message, "error"); }
}


// ─────────────────────────────────────────────────────────────────
// 15. SKILLS
// ─────────────────────────────────────────────────────────────────

async function loadSkills() {
  el("skills-list").innerHTML = `<div class="loading-text">Loading skills…</div>`;
  try {
    const res = await state.client.request("skills.status", {});
    const skills = res.skills || res || [];
    state.skills = skills;

    const render = (f) => {
      const filtered = f
        ? skills.filter(s => (s.key||s.name||"").toLowerCase().includes(f) || (s.description||"").toLowerCase().includes(f))
        : skills;
      el("skills-list").innerHTML = filtered.map(s => {
        const enabled = s.enabled !== false;
        const key = s.key || s.name || "?";
        return `
          <div class="skill-card ${enabled ? "enabled" : ""}">
            <div class="skill-header">
              <div class="skill-name">${escHtml(s.name || key)}</div>
              <button class="skill-toggle ${enabled ? "on" : "off"}"
                      onclick="toggleSkill('${escHtml(key)}', ${!enabled})"
                      title="${enabled ? "Disable" : "Enable"}"></button>
            </div>
            ${s.description ? `<div class="skill-desc">${escHtml(s.description)}</div>` : ""}
            <div class="skill-meta">
              <span class="skill-key">${escHtml(key)}</span>
              ${s.version ? `<span class="model-chip">${escHtml(s.version)}</span>` : ""}
              ${s.hasApiKey ? `<span class="model-chip" style="color:var(--accent);border-color:var(--accent)">API KEY SET</span>` : ""}
            </div>
          </div>`;
      }).join("") || `<div class="empty-state"><strong>NO MATCH</strong></div>`;
    };
    render("");
    el("skills-search").oninput = (e) => render(e.target.value.trim().toLowerCase());
  } catch (e) {
    el("skills-list").innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}

async function toggleSkill(skillKey, enabled) {
  try {
    await state.client.request("skills.update", { skillKey, enabled });
    toast(`Skill ${enabled ? "enabled" : "disabled"}`, "success");
    loadSkills();
  } catch (e) { toast("Toggle failed: " + e.message, "error"); }
}


// ─────────────────────────────────────────────────────────────────
// 16. DEVICES
// ─────────────────────────────────────────────────────────────────

async function loadDevices() {
  el("device-pair-requests").innerHTML = "";
  el("devices-list").innerHTML = `<div class="loading-text">Loading devices…</div>`;
  try {
    const pairRes = await state.client.request("devices.pair.list", {});
    const requests = pairRes.requests || pairRes || [];
    state.devicePairRequests = requests;

    const pendingEl = el("device-pair-pending");
    if (requests.length > 0) {
      pendingEl.textContent = `${requests.length} pending`;
      pendingEl.classList.remove("hidden");
      el("device-pair-requests").innerHTML = requests.map(r => `
        <div class="device-pair-card">
          <div class="device-pair-info">
            <div class="device-pair-name">${escHtml(r.displayName || r.deviceId)}</div>
            <div class="device-pair-meta">${escHtml(r.platform || "")} · ${escHtml(r.clientMode || r.role || "")} · ip: ${escHtml(r.remoteIp || "?")}</div>
          </div>
          <div class="device-pair-actions">
            <button class="btn-approve" onclick="approveDevicePair('${escHtml(r.requestId)}','${escHtml(r.displayName||r.deviceId)}')">✓ Approve</button>
            <button class="btn-danger sm" onclick="rejectDevicePair('${escHtml(r.requestId)}')">✕ Reject</button>
          </div>
        </div>`).join("");
    } else {
      pendingEl.classList.add("hidden");
      el("device-pair-requests").innerHTML = `<div style="padding:8px 0;color:var(--text-dim);font-size:12px;font-family:var(--font-mono)">No pending pair requests</div>`;
    }
  } catch (e) {
    el("device-pair-requests").innerHTML = `<div style="color:var(--error);font-size:12px;padding:8px 0">${escHtml(e.message)}</div>`;
  }

  // Paired devices — try snapshot presence for device info
  try {
    const snap = state.snapshot || await state.client.request("snapshot", {});
    const presence = (snap.presence || []).filter(p => p.deviceId);
    if (presence.length === 0) {
      el("devices-list").innerHTML = `<div class="empty-state"><strong>NO PAIRED DEVICES</strong>Devices appear after pairing</div>`;
    } else {
      el("devices-list").innerHTML = presence.map(p => `
        <div class="device-row">
          <div class="device-name">${escHtml(p.host || p.ip || p.deviceId)}</div>
          <div class="device-platform">${escHtml(p.platform || "")}</div>
          <div class="device-role">${escHtml(p.mode || p.roles?.[0] || "?")}</div>
          <div style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim)">${escHtml(p.version || "")}</div>
        </div>`).join("");
    }
  } catch (e) {
    el("devices-list").innerHTML = `<div class="empty-state"><strong>ERROR</strong>${escHtml(e.message)}</div>`;
  }
}

async function approveDevicePair(requestId, name) {
  try {
    await state.client.request("devices.pair.approve", { requestId });
    toast(`Approved: ${name}`, "success");
    loadDevices();
  } catch (e) { toast("Approve failed: " + e.message, "error"); }
}

async function rejectDevicePair(requestId) {
  try {
    await state.client.request("devices.pair.reject", { requestId });
    toast("Rejected", "info");
    loadDevices();
  } catch (e) { toast("Reject failed: " + e.message, "error"); }
}


// ─────────────────────────────────────────────────────────────────
// 17. USAGE
// ─────────────────────────────────────────────────────────────────

async function loadUsage() {
  el("usage-summary").innerHTML = `<div class="loading-text" style="grid-column:1/-1">Loading usage…</div>`;
  el("usage-sessions").innerHTML = "";

  const days = parseInt(el("usage-range")?.value || "30", 10);
  const endDate = new Date();
  const startDate = new Date(Date.now() - days * 86400_000);
  const fmt = (d) => d.toISOString().slice(0, 10);

  try {
    const res = await state.client.request("sessions.usage", {
      startDate: fmt(startDate),
      endDate: fmt(endDate),
      limit: 100,
    });

    const sessions = res.sessions || res || [];
    const totalTokens = sessions.reduce((s, x) => s + (x.totalTokens || 0), 0);
    const totalCostCents = sessions.reduce((s, x) => s + (x.costCents || 0), 0);
    const totalMessages = sessions.reduce((s, x) => s + (x.messageCount || 0), 0);

    el("usage-summary").innerHTML = `
      <div class="usage-stat">
        <div class="usage-stat-label">SESSIONS</div>
        <div class="usage-stat-value">${sessions.length}</div>
        <div class="usage-stat-sub">last ${days} days</div>
      </div>
      <div class="usage-stat">
        <div class="usage-stat-label">TOKENS</div>
        <div class="usage-stat-value">${fmtTokens(totalTokens)}</div>
        <div class="usage-stat-sub">in + out</div>
      </div>
      <div class="usage-stat">
        <div class="usage-stat-label">MESSAGES</div>
        <div class="usage-stat-value">${fmtTokens(totalMessages)}</div>
        <div class="usage-stat-sub">total turns</div>
      </div>
      <div class="usage-stat">
        <div class="usage-stat-label">EST. COST</div>
        <div class="usage-stat-value">${fmtCost(totalCostCents)}</div>
        <div class="usage-stat-sub">USD</div>
      </div>`;

    if (!sessions.length) {
      el("usage-sessions").innerHTML = `<div class="empty-state"><strong>NO DATA</strong>No usage recorded in this period</div>`;
      return;
    }

    el("usage-sessions").innerHTML = `
      <table class="usage-table">
        <thead>
          <tr>
            <th>Session</th><th>Agent</th><th>Messages</th>
            <th>Tokens</th><th>Cost</th><th>Last Active</th>
          </tr>
        </thead>
        <tbody>
          ${sessions.map(s => `
            <tr>
              <td class="key-cell">${escHtml(s.key || "—")}</td>
              <td>${escHtml(s.agentId || "—")}</td>
              <td>${s.messageCount ?? "—"}</td>
              <td>${fmtTokens(s.totalTokens || 0)}</td>
              <td class="cost-cell">${fmtCost(s.costCents || 0)}</td>
              <td>${fmtDate(s.lastActiveMs || s.updatedAtMs)}</td>
            </tr>`).join("")}
        </tbody>
      </table>`;
  } catch (e) {
    el("usage-summary").innerHTML = `<div class="empty-state" style="grid-column:1/-1"><strong>UNAVAILABLE</strong>${escHtml(e.message)}</div>`;
  }
}


// ─────────────────────────────────────────────────────────────────
// 18. GATEWAY EVENTS
// ─────────────────────────────────────────────────────────────────

function handleGatewayEvent(frame) {
  const ev = frame.event;
  const data = frame.data || {};

  if (ev === "exec.approval.requested") {
    // Push to pending queue
    if (!state.pendingApprovals.find(r => r.id === data.id)) {
      state.pendingApprovals.push(data);
    }
    // Update badge
    const badge = el("approval-badge");
    badge.textContent = state.pendingApprovals.length;
    badge.classList.remove("hidden");
    // If approvals view is open, re-render queue
    if (!el("view-approvals").classList.contains("hidden")) {
      renderApprovalQueue();
    }
    toast(`Approval requested: ${(data.command || "").slice(0, 60)}`, "info", 6000);
  }

  if (ev === "exec.approval.resolved") {
    state.pendingApprovals = state.pendingApprovals.filter(r => r.id !== data.id);
    if (!el("view-approvals").classList.contains("hidden")) renderApprovalQueue();
    const badge = el("approval-badge");
    if (state.pendingApprovals.length === 0) badge.classList.add("hidden");
    else badge.textContent = state.pendingApprovals.length;
  }

  if (ev === "devices.pair.requested") {
    if (!el("view-devices").classList.contains("hidden")) loadDevices();
    toast(`Device pair request: ${data.displayName || data.deviceId}`, "info", 8000);
  }

  if (ev === "tick" || ev === "snapshot") {
    if (data.uptimeMs != null) state.snapshot = { ...state.snapshot, ...data };
  }
}


// ─────────────────────────────────────────────────────────────────
// 19. CONNECT FLOW
// ─────────────────────────────────────────────────────────────────

async function doConnect() {
  const url      = el("inp-url").value.trim();
  const token    = el("inp-token").value.trim();
  const password = el("inp-password").value.trim();
  if (!url) { showConnectError("Gateway URL is required"); return; }

  el("btn-connect").disabled = true;
  el("btn-connect").textContent = "Connecting…";
  el("connect-error").classList.add("hidden");

  const client = new GatewayClient({
    url, token: token || undefined, password: password || undefined,
    onEvent: handleGatewayEvent,
    onConnect: (hello) => {
      setStatus("connected", url.replace(/^wss?:\/\//, ""));
      // Show server version in sidebar
      if (hello?.server?.version) {
        el("gateway-info").innerHTML = `${url.replace(/^wss?:\/\//,"")}<br>v${escHtml(hello.server.version)}`;
      }
    },
    onDisconnect: (code, reason) => {
      setStatus("error", "disconnected");
      toast(`Disconnected (${code}): ${reason}`, "error");
    },
    onError: () => {},
  });

  try {
    await client.connect();
    state.client = client;
    localStorage.setItem("mc-url", url);
    if (token) localStorage.setItem("mc-token", token);

    el("connect-overlay").classList.remove("active");
    el("shell").classList.remove("hidden");
    setStatus("connected", url.replace(/^wss?:\/\//, ""));

    await loadAgentsSummary().catch(() => {});
    navigate("overview");

  } catch (e) {
    el("btn-connect").disabled = false;
    el("btn-connect").textContent = "Connect";
    const msg = e.message || "Connection failed";
    el("connect-error").textContent = msg;
    el("connect-error").classList.remove("hidden");
  }
}

function doDisconnect() {
  if (state.client) { state.client.disconnect(); state.client = null; }
  clearInterval(logPollInterval); logPollInterval = null;
  clearInterval(approvalPollInterval); approvalPollInterval = null;
  Object.assign(state, {
    snapshot: null, agents: [], sessions: [], channels: {},
    cron: [], models: [], nodes: [], config: null,
    logLines: [], logCursor: 0, pendingApprovals: [],
    approvalsPolicy: null, skills: [], devicePairRequests: [], devices: [],
  });
  el("shell").classList.add("hidden");
  el("connect-overlay").classList.add("active");
  el("btn-connect").disabled = false;
  el("btn-connect").textContent = "Connect";
  el("approval-badge").classList.add("hidden");
  setStatus("connecting", "Disconnected");
}


// ─────────────────────────────────────────────────────────────────
// 20. INIT
// ─────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  // Restore saved settings
  const savedUrl   = localStorage.getItem("mc-url");
  const savedToken = localStorage.getItem("mc-token");
  if (savedUrl)   el("inp-url").value   = savedUrl;
  if (savedToken) el("inp-token").value = savedToken;

  // Connect
  el("btn-connect").addEventListener("click", doConnect);
  ["inp-url","inp-token","inp-password"].forEach(id => {
    el(id).addEventListener("keydown", e => { if (e.key === "Enter") doConnect(); });
  });

  // Nav
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => navigate(btn.dataset.view));
  });

  // Disconnect
  el("btn-disconnect").addEventListener("click", doDisconnect);

  // Action buttons
  el("btn-create-agent").addEventListener("click", openCreateAgent);
  el("btn-add-cron").addEventListener("click", openAddCron);
  el("btn-save-config").addEventListener("click", saveConfig);
  el("btn-clear-logs").addEventListener("click", () => {
    el("logs-output").innerHTML = "";
    state.logLines = [];
  });
  el("btn-refresh-approvals").addEventListener("click", loadApprovals);
  el("btn-refresh-usage").addEventListener("click", loadUsage);
  el("usage-range").addEventListener("change", loadUsage);

  // Logs follow
  el("logs-follow").addEventListener("change", e => {
    state.logFollowing = e.target.checked;
    if (state.logFollowing) el("logs-output").scrollTop = el("logs-output").scrollHeight;
  });

  // Session search
  el("sessions-search").addEventListener("input", e => {
    const q = e.target.value.trim().toLowerCase();
    renderSessions(!q ? state.sessions : state.sessions.filter(s =>
      (s.key||"").toLowerCase().includes(q) ||
      (s.agentId||"").toLowerCase().includes(q) ||
      (s.derivedTitle||"").toLowerCase().includes(q)
    ));
  });

  // Expose for inline onclick handlers
  Object.assign(window, {
    openAgentEdit, openAgentFiles, openFileEdit, openAgentPolicy,
    confirmDeleteAgent, openSessionDetail, confirmDeleteSession,
    runCronNow, editCronJob, confirmDeleteCron,
    resolveApproval, editDefaultPolicy, removeAllowlistEntry,
    toggleSkill, approveDevicePair, rejectDevicePair,
  });
});
