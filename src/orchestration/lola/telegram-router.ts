import type { TelegramRoutingDecision } from "./telegram-types.js";

const CTO_KEYWORDS = [
  "repo",
  "github",
  "pull request",
  "pr",
  "ci",
  "test",
  "build",
  "deployment",
  "deploy",
  "bug",
  "engineering",
  "code",
  "fix",
  "infrastructure",
  "infra",
  "check repo health",
  "wire telegram",
  "run tests",
  "update the repo",
];

const LOLA_KEYWORDS = [
  "calendar",
  "meeting",
  "follow-up",
  "follow up",
  "inbox",
  "attio",
  "outlook",
  "recap",
  "followups",
];
export const GRAPH_OPERATION_KEYWORDS = new Set(LOLA_KEYWORDS);
const RESEARCH_KEYWORDS = ["research", "analyze", "analysis", "synthesize", "synthesis"];
const WORKFLOW_KEYWORDS = ["automation", "workflow", "runbook", "trigger", "reconcile"];
const BLOCKED_KEYWORDS = [
  "rm -rf",
  "privilege escalation",
  "retrieve secret",
  "cat ~/.ssh",
  "raw shell",
];

function containsAny(text: string, keywords: string[]): string | null {
  const hit = keywords.find((keyword) => text.includes(keyword));
  return hit ?? null;
}

export function routeTelegramRequest(text: string): TelegramRoutingDecision {
  const normalized = text.trim().toLowerCase();

  const blocked = containsAny(normalized, BLOCKED_KEYWORDS);
  if (blocked) {
    return {
      target: "blocked",
      intent: "blocked",
      executor: "blocked",
      reason: `blocked keyword: ${blocked}`,
    };
  }

  const ctoHit = containsAny(normalized, CTO_KEYWORDS);
  if (ctoHit) {
    return {
      target: "cto",
      intent: "engineering",
      executor: "repo_executor",
      reason: `engineering keyword: ${ctoHit}`,
    };
  }

  const lolaHit = containsAny(normalized, LOLA_KEYWORDS);
  if (lolaHit) {
    return {
      target: "workflow_runner",
      intent: "operations",
      executor: "workflow_engine",
      reason: `operations keyword: ${lolaHit}`,
    };
  }

  const researchHit = containsAny(normalized, RESEARCH_KEYWORDS);
  if (researchHit) {
    return {
      target: "research",
      intent: "research",
      executor: "research_agent",
      reason: `research keyword: ${researchHit}`,
    };
  }

  const workflowHit = containsAny(normalized, WORKFLOW_KEYWORDS);
  if (workflowHit) {
    return {
      target: "workflow_runner",
      intent: "operations",
      executor: "workflow_engine",
      reason: `workflow keyword: ${workflowHit}`,
    };
  }

  return {
    target: "lola",
    intent: "communication",
    executor: "conversational",
    reason: "general communication default route",
  };
}
