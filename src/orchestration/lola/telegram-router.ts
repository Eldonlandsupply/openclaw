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
];

const LOLA_KEYWORDS = ["calendar", "meeting", "follow-up", "follow up", "inbox", "assistant"];
const RESEARCH_KEYWORDS = ["research", "analyze", "analysis", "synthesize", "synthesis"];
const WORKFLOW_KEYWORDS = ["automation", "workflow", "runbook", "trigger"];
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
    return { target: "blocked", reason: `blocked keyword: ${blocked}` };
  }

  const ctoHit = containsAny(normalized, CTO_KEYWORDS);
  if (ctoHit) {
    return { target: "cto", reason: `engineering keyword: ${ctoHit}` };
  }

  const lolaHit = containsAny(normalized, LOLA_KEYWORDS);
  if (lolaHit) {
    return { target: "lola", reason: `assistant keyword: ${lolaHit}` };
  }

  const researchHit = containsAny(normalized, RESEARCH_KEYWORDS);
  if (researchHit) {
    return { target: "research", reason: `research keyword: ${researchHit}` };
  }

  const workflowHit = containsAny(normalized, WORKFLOW_KEYWORDS);
  if (workflowHit) {
    return { target: "workflow_runner", reason: `workflow keyword: ${workflowHit}` };
  }

  return { target: "lola", reason: "default lola front-door route" };
}
