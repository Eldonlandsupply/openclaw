import path from "node:path";
import { fileURLToPath } from "node:url";
import type { OpenClawConfig } from "../config/config.js";
import type { AgentBootstrapHookContext } from "../hooks/internal-hooks.js";
import type { WorkspaceBootstrapFile } from "./workspace.js";
import { createInternalHookEvent, triggerInternalHook } from "../hooks/internal-hooks.js";
import { resolveAgentIdFromSessionKey } from "../routing/session-key.js";

/** Supported role kit identifiers. */
const VALID_ROLE_KITS = new Set([
  "researcher",
  "operator",
  "auditor",
  "repo-agent",
  "chief-of-staff",
]);

function resolveRoleKitsDir(): string {
  // Resolve relative to this file: src/agents/role-kits/
  const thisDir = path.dirname(fileURLToPath(import.meta.url));
  return path.join(thisDir, "role-kits");
}

async function loadRoleKitFile(kitsDir: string, fileName: string): Promise<string | null> {
  const { readFile } = await import("node:fs/promises");
  const filePath = path.join(kitsDir, fileName);
  try {
    return await readFile(filePath, "utf-8");
  } catch {
    return null;
  }
}

/**
 * Resolves the roleKit for a given agentId from config.
 * Returns null if not configured or not a recognised kit.
 */
function resolveRoleKit(
  cfg: OpenClawConfig | undefined,
  agentId: string | undefined,
): string | null {
  if (!cfg || !agentId) {
    return null;
  }
  const entry = (cfg.agents?.list ?? []).find(
    (a) => a?.id?.toLowerCase() === agentId.toLowerCase(),
  );
  const kit = entry?.roleKit?.trim().toLowerCase();
  if (!kit || !VALID_ROLE_KITS.has(kit)) {
    return null;
  }
  return kit;
}

/**
 * Prepend lean role-kit bootstrap files (AGENTS.md, TOOLS.md) before the
 * workspace files. These are injected as synthetic WorkspaceBootstrapFile
 * entries so they survive the subagent allowlist filter that follows.
 *
 * Injection strategy:
 * - Role-kit AGENTS.md is prepended before any existing AGENTS.md
 * - Role-kit TOOLS.md is prepended before any existing TOOLS.md
 * - If the workspace file already exists it is kept after the kit file,
 *   giving the operator the final word via their workspace copy.
 */
async function injectRoleKitFiles(
  files: WorkspaceBootstrapFile[],
  cfg: OpenClawConfig | undefined,
  agentId: string | undefined,
): Promise<WorkspaceBootstrapFile[]> {
  const kit = resolveRoleKit(cfg, agentId);
  if (!kit) {
    return files;
  }

  const kitsDir = resolveRoleKitsDir();
  const [agentsMd, toolsMd] = await Promise.all([
    loadRoleKitFile(kitsDir, `${kit}/AGENTS.md`),
    loadRoleKitFile(kitsDir, `${kit}/TOOLS.md`),
  ]);

  if (!agentsMd && !toolsMd) {
    return files;
  }

  const injected: WorkspaceBootstrapFile[] = [];

  if (agentsMd) {
    injected.push({
      name: "AGENTS.md",
      path: path.join(kitsDir, kit, "AGENTS.md"),
      content: `<!-- role-kit: ${kit} -->\n${agentsMd}`,
      missing: false,
    });
  }

  if (toolsMd) {
    injected.push({
      name: "TOOLS.md",
      path: path.join(kitsDir, kit, "TOOLS.md"),
      content: `<!-- role-kit: ${kit} -->\n${toolsMd}`,
      missing: false,
    });
  }

  // Merge: kit files first, workspace files after (workspace wins on conflicts
  // by position — the runner uses head+tail trimming so earlier content is
  // preferred; operators can override by having larger workspace files).
  return [...injected, ...files];
}

export async function applyBootstrapHookOverrides(params: {
  files: WorkspaceBootstrapFile[];
  workspaceDir: string;
  config?: OpenClawConfig;
  sessionKey?: string;
  sessionId?: string;
  agentId?: string;
}): Promise<WorkspaceBootstrapFile[]> {
  const sessionKey = params.sessionKey ?? params.sessionId ?? "unknown";
  const agentId =
    params.agentId ??
    (params.sessionKey ? resolveAgentIdFromSessionKey(params.sessionKey) : undefined);
  const context: AgentBootstrapHookContext = {
    workspaceDir: params.workspaceDir,
    bootstrapFiles: params.files,
    cfg: params.config,
    sessionKey: params.sessionKey,
    sessionId: params.sessionId,
    agentId,
  };
  const event = createInternalHookEvent("agent", "bootstrap", sessionKey, context);
  await triggerInternalHook(event);
  const afterHook = (event.context as AgentBootstrapHookContext).bootstrapFiles;
  const resolved = Array.isArray(afterHook) ? afterHook : params.files;

  // Role-kit injection runs after plugin hooks so plugins can still mutate the
  // base file list without needing kit awareness.
  return injectRoleKitFiles(resolved, params.config, agentId);
}
