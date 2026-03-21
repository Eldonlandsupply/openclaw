import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { z } from "zod";

const execFileAsync = promisify(execFile);

export const GH_COMMAND_FAMILIES = [
  "auth",
  "repo",
  "pr",
  "issue",
  "search",
  "workflow",
  "run",
  "release",
  "project",
  "api",
  "gist",
  "secret",
  "variable",
  "label",
  "alias",
  "extension",
  "ruleset",
  "codespace",
  "org",
  "browse",
  "status",
  "cache",
  "attestation",
] as const;

export type GhCommandFamily = (typeof GH_COMMAND_FAMILIES)[number];
export type GithubIntent = "read" | "write" | "admin" | "dangerous";
export type GithubRiskLevel = "low" | "medium" | "high" | "critical";
export type GithubExecutionStatus = "pending" | "approved" | "blocked" | "executed" | "failed";

export const GitHubTargetScopeSchema = z
  .object({
    owner: z.string().min(1),
    repo: z.string().min(1).optional(),
    branch: z.string().min(1).optional(),
    baseBranch: z.string().min(1).optional(),
  })
  .strict();

export const GitHubActionRequestSchema = z
  .object({
    requestId: z.string().min(1),
    sourceAgent: z.string().min(1),
    userIdentity: z.string().min(1),
    targetScope: GitHubTargetScopeSchema,
    naturalLanguageRequest: z.string().min(1),
    requestingChannel: z.string().min(1),
    preApproved: z.boolean().default(false),
    approvalPolicy: z
      .object({
        allowAutoApproveWrites: z.boolean().default(false),
        allowAutoApproveHighRisk: z.boolean().default(false),
        allowMessagingWrites: z.boolean().default(false),
      })
      .default({}),
  })
  .strict();

export const GitHubActionPlanSchema = z
  .object({
    requestId: z.string().min(1),
    sourceAgent: z.string().min(1),
    userIdentity: z.string().min(1),
    targetScope: GitHubTargetScopeSchema,
    intent: z.enum(["read", "write", "admin", "dangerous"]),
    commandFamily: z.enum(GH_COMMAND_FAMILIES),
    proposedAction: z.string().min(1),
    ghCommandPlan: z.array(z.string().min(1)).min(1),
    riskLevel: z.enum(["low", "medium", "high", "critical"]),
    approvalRequired: z.boolean(),
    executionStatus: z.enum(["pending", "approved", "blocked", "executed", "failed"]),
    auditLogRequired: z.boolean().default(true),
    rollbackPlan: z.string().min(1).optional(),
    browserRejectedReason: z.string().min(1),
    commandCatalog: z.array(z.string().min(1)).default([]),
    expectedOutcome: z.string().min(1),
  })
  .strict();

export const GitHubAuditEntrySchema = z
  .object({
    timestamp: z.string().min(1),
    sourceAgent: z.string().min(1),
    requestingChannel: z.string().min(1),
    resolvedActor: z.string().min(1),
    repoScope: z.string().min(1),
    executedCommands: z.array(z.string()).default([]),
    stdoutSummary: z.string(),
    stderrSummary: z.string(),
    riskLevel: z.enum(["low", "medium", "high", "critical"]),
    approvalSource: z.string().min(1),
    result: z.enum(["success", "failure", "blocked"]),
  })
  .strict();

export type GitHubActionRequest = z.infer<typeof GitHubActionRequestSchema>;
export type GitHubActionPlan = z.infer<typeof GitHubActionPlanSchema>;
export type GitHubAuditEntry = z.infer<typeof GitHubAuditEntrySchema>;

const MESSAGING_CHANNELS = new Set(["whatsapp", "imessage", "sms", "slack", "teams"]);
const DANGEROUS_PATTERNS = [
  /delete\s+(this\s+)?repo/i,
  /delete\s+release/i,
  /delete\s+tag/i,
  /change\s+auth/i,
  /show\s+(me\s+)?secret/i,
  /print\s+(the\s+)?token/i,
  /force\s+push/i,
  /branch\s+protection/i,
  /ruleset/i,
  /set\s+secret/i,
  /set\s+variable/i,
] as const;

const HIGH_RISK_PATTERNS = [
  /merge\s+pr/i,
  /close\s+issue/i,
  /rerun\s+workflow/i,
  /update\s+branch/i,
] as const;
const WRITE_PATTERNS = [
  /create\s+(a\s+)?draft\s+pr/i,
  /open\s+(a\s+)?draft\s+pr/i,
  /comment\s+on\s+issue/i,
  /assign\s+reviewers/i,
  /create\s+label/i,
  /create\s+(a\s+)?draft\s+release/i,
] as const;

interface DiscoveryResult {
  version?: string;
  families: string[];
}

export async function discoverGhCommandCatalog(params?: {
  exec?: typeof execFileAsync;
}): Promise<DiscoveryResult> {
  const run = params?.exec ?? execFileAsync;
  const [help, reference] = await Promise.all([
    run("gh", ["--help"], { maxBuffer: 1024 * 1024 }),
    run("gh", ["help", "reference"], { maxBuffer: 1024 * 1024 }),
  ]);
  const families = new Set<string>();
  for (const line of `${help.stdout}\n${reference.stdout}`.split("\n")) {
    const match = line.match(/^\s{0,4}([a-z][a-z0-9-]+)\s{2,}/i);
    if (match) {
      families.add(match[1]);
    }
  }
  return {
    version: help.stdout.match(/GitHub CLI\s+([\w.-]+)/i)?.[1],
    families: [...families],
  };
}

export function buildGitHubActionPlan(
  request: GitHubActionRequest,
  catalog?: DiscoveryResult,
): GitHubActionPlan {
  const parsed = GitHubActionRequestSchema.parse(request);
  const normalized = parsed.naturalLanguageRequest.trim();
  const lower = normalized.toLowerCase();
  const commandFamily = resolveCommandFamily(lower);
  const intent = classifyIntent(lower, commandFamily);
  const riskLevel = classifyRisk(lower, intent, commandFamily);
  const approvalRequired = shouldRequireApproval({
    request: parsed,
    intent,
    riskLevel,
  });

  const ghCommandPlan = buildCommandPlan({
    request: parsed,
    family: commandFamily,
    lower,
  });

  const executionStatus: GithubExecutionStatus = approvalRequired
    ? parsed.preApproved
      ? "approved"
      : riskLevel === "critical"
        ? "blocked"
        : "pending"
    : "approved";

  return GitHubActionPlanSchema.parse({
    requestId: parsed.requestId,
    sourceAgent: parsed.sourceAgent,
    userIdentity: parsed.userIdentity,
    targetScope: parsed.targetScope,
    intent,
    commandFamily,
    proposedAction: summarizeAction(normalized, commandFamily),
    ghCommandPlan,
    riskLevel,
    approvalRequired,
    executionStatus,
    auditLogRequired: true,
    rollbackPlan: buildRollbackPlan(commandFamily, intent, lower),
    browserRejectedReason:
      "Browser rejected because GitHub CLI provides a direct, auditable system interface for this request.",
    commandCatalog: (catalog?.families ?? []).filter((family) =>
      GH_COMMAND_FAMILIES.includes(family as GhCommandFamily),
    ),
    expectedOutcome: describeOutcome(commandFamily, lower),
  });
}

export function createGitHubAuditEntry(params: {
  plan: GitHubActionPlan;
  requestingChannel: string;
  executedCommands: string[];
  stdoutSummary: string;
  stderrSummary: string;
  result: GitHubAuditEntry["result"];
  approvalSource: string;
  timestamp?: string;
}): GitHubAuditEntry {
  return GitHubAuditEntrySchema.parse({
    timestamp: params.timestamp ?? new Date().toISOString(),
    sourceAgent: params.plan.sourceAgent,
    requestingChannel: params.requestingChannel,
    resolvedActor: params.plan.userIdentity,
    repoScope: formatScope(params.plan.targetScope),
    executedCommands: params.executedCommands,
    stdoutSummary: params.stdoutSummary,
    stderrSummary: params.stderrSummary,
    riskLevel: params.plan.riskLevel,
    approvalSource: params.approvalSource,
    result: params.result,
  });
}

function resolveCommandFamily(lower: string): GhCommandFamily {
  if (lower.includes("pull request") || /\bpr\b/.test(lower)) {
    return "pr";
  }
  if (lower.includes("issue")) {
    return "issue";
  }
  if (lower.includes("workflow") || lower.includes("run ")) {
    return lower.includes("workflow") ? "workflow" : "run";
  }
  if (lower.includes("release") || lower.includes("asset")) {
    return "release";
  }
  if (lower.includes("project")) {
    return "project";
  }
  if (lower.includes("secret")) {
    return "secret";
  }
  if (lower.includes("variable")) {
    return "variable";
  }
  if (lower.includes("label")) {
    return "label";
  }
  if (lower.includes("codespace")) {
    return "codespace";
  }
  if (lower.includes("org ") || lower.startsWith("org")) {
    return "org";
  }
  if (lower.includes("search")) {
    return "search";
  }
  if (lower.includes("api")) {
    return "api";
  }
  if (lower.includes("repo") || lower.includes("repository")) {
    return "repo";
  }
  return "api";
}

function classifyIntent(lower: string, family: GhCommandFamily): GithubIntent {
  if (DANGEROUS_PATTERNS.some((pattern) => pattern.test(lower))) {
    return "dangerous";
  }
  if (["secret", "variable", "ruleset", "auth"].includes(family)) {
    return lower.includes("list") || lower.includes("show") || lower.includes("view")
      ? "read"
      : "admin";
  }
  if (HIGH_RISK_PATTERNS.some((pattern) => pattern.test(lower))) {
    return "admin";
  }
  if (WRITE_PATTERNS.some((pattern) => pattern.test(lower))) {
    return "write";
  }
  if (/(create|open|comment|assign|edit|update|rerun|dispatch|trigger)/i.test(lower)) {
    return "write";
  }
  return "read";
}

function classifyRisk(
  lower: string,
  intent: GithubIntent,
  family: GhCommandFamily,
): GithubRiskLevel {
  if (
    DANGEROUS_PATTERNS.some((pattern) => pattern.test(lower)) ||
    ["secret", "variable", "ruleset", "auth"].includes(family)
  ) {
    return lower.includes("list") || lower.includes("view") ? "high" : "critical";
  }
  if (HIGH_RISK_PATTERNS.some((pattern) => pattern.test(lower)) || intent === "admin") {
    return "high";
  }
  if (intent === "write") {
    return "medium";
  }
  return "low";
}

function shouldRequireApproval(params: {
  request: GitHubActionRequest;
  intent: GithubIntent;
  riskLevel: GithubRiskLevel;
}): boolean {
  if (params.riskLevel === "critical") {
    return true;
  }
  if (
    MESSAGING_CHANNELS.has(params.request.requestingChannel.toLowerCase()) &&
    params.riskLevel !== "low"
  ) {
    return !params.request.approvalPolicy.allowMessagingWrites;
  }
  if (params.riskLevel === "high") {
    return !params.request.preApproved || !params.request.approvalPolicy.allowAutoApproveHighRisk;
  }
  if (params.intent === "write") {
    return !params.request.preApproved && !params.request.approvalPolicy.allowAutoApproveWrites;
  }
  return false;
}

function buildCommandPlan(params: {
  request: GitHubActionRequest;
  family: GhCommandFamily;
  lower: string;
}): string[] {
  const repoArg = params.request.targetScope.repo
    ? `--repo ${params.request.targetScope.owner}/${params.request.targetScope.repo}`
    : `--repo ${params.request.targetScope.owner}`;
  const branch = params.request.targetScope.branch;
  const baseBranch = params.request.targetScope.baseBranch;

  if (
    params.family === "pr" &&
    /create|open/.test(params.lower) &&
    params.lower.includes("draft")
  ) {
    return [
      `gh pr create ${repoArg} --base ${baseBranch ?? "main"} --head ${branch ?? "UNKNOWN_HEAD"} --draft --title "TITLE" --body-file BODY.md`,
    ];
  }
  if (params.family === "pr" && params.lower.includes("list")) {
    return [`gh pr list ${repoArg} --state open`];
  }
  if (params.family === "issue" && params.lower.includes("comment")) {
    const issueNumber = extractFirstNumber(params.lower) ?? "ISSUE_NUMBER";
    return [`gh issue comment ${issueNumber} ${repoArg} --body-file COMMENT.md`];
  }
  if (
    params.family === "workflow" &&
    (params.lower.includes("failed") || params.lower.includes("today"))
  ) {
    return [`gh run list ${repoArg} --status failure --limit 20`];
  }
  if (params.family === "workflow" && /run|trigger|dispatch/.test(params.lower)) {
    return [`gh workflow run WORKFLOW.yml ${repoArg}${branch ? ` --ref ${branch}` : ""}`];
  }
  if (params.family === "release" && params.lower.includes("asset")) {
    return [`gh release download ${repoArg} --pattern "ASSET_PATTERN"`];
  }
  if (params.family === "release" && params.lower.includes("draft")) {
    return [`gh release create TAG ${repoArg} --draft --title "TITLE" --notes-file NOTES.md`];
  }
  if (params.family === "search" && params.lower.includes("repo")) {
    return [`gh search repos "QUERY" --owner ${params.request.targetScope.owner}`];
  }
  if (params.family === "repo" && params.lower.includes("template")) {
    return [
      `gh repo create ${params.request.targetScope.owner}/NEW_REPO --private --template TEMPLATE_OWNER/TEMPLATE_REPO`,
    ];
  }
  if (params.family === "secret") {
    return [
      params.lower.includes("list")
        ? `gh secret list ${repoArg}`
        : `gh secret set NAME ${repoArg} --body "VALUE"`,
    ];
  }
  if (params.family === "variable") {
    return [
      params.lower.includes("list")
        ? `gh variable list ${repoArg}`
        : `gh variable set NAME ${repoArg} --body "VALUE"`,
    ];
  }
  if (params.family === "api") {
    return [`gh api ${extractApiPath(params.lower)}`];
  }
  return [`gh ${params.family} --help`];
}

function summarizeAction(request: string, family: GhCommandFamily): string {
  const cleaned = request.replace(/\s+/g, " ").trim();
  return `${family.toUpperCase()}: ${cleaned}`;
}

function buildRollbackPlan(
  family: GhCommandFamily,
  intent: GithubIntent,
  lower: string,
): string | undefined {
  if (intent === "read") {
    return "No rollback required for read-only execution.";
  }
  if (family === "pr") {
    return lower.includes("draft")
      ? "Close the draft PR or edit it before review if the generated metadata is wrong."
      : "Revert the PR-side metadata or post a corrective follow-up comment.";
  }
  if (family === "issue") {
    return "Post a corrective follow-up comment or edit the issue fields back to their prior values.";
  }
  if (family === "workflow") {
    return "Disable downstream deployment steps or cancel the run if it was triggered incorrectly.";
  }
  if (family === "release") {
    return "Delete the draft release before publication.";
  }
  return "Use the matching gh edit/delete flow only after explicit approval.";
}

function describeOutcome(family: GhCommandFamily, lower: string): string {
  if (family === "workflow" && lower.includes("failed")) {
    return "Return the most recent failed workflow runs for operator review.";
  }
  if (family === "pr" && lower.includes("draft")) {
    return "Create a draft pull request without merging or changing branch protections.";
  }
  if (family === "issue" && lower.includes("comment")) {
    return "Post the requested comment onto the target issue.";
  }
  if (family === "search") {
    return "Return matching repositories or code results from GitHub search.";
  }
  return `Execute the requested ${family} action through GitHub CLI.`;
}

function formatScope(scope: z.infer<typeof GitHubTargetScopeSchema>): string {
  return [scope.owner, scope.repo, scope.branch ? `branch=${scope.branch}` : undefined]
    .filter(Boolean)
    .join("/");
}

function extractFirstNumber(text: string): string | undefined {
  return text.match(/\b(\d+)\b/)?.[1];
}

function extractApiPath(lower: string): string {
  const direct = lower.match(/\/(repos|orgs|user|search)[^\s]*/);
  if (direct) {
    return direct[0];
  }
  return "RATE_LIMIT_ENDPOINT";
}
