import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export type ChangeCategory =
  | "security"
  | "bug fix"
  | "reliability"
  | "performance"
  | "cost efficiency"
  | "developer experience"
  | "UI/dashboard"
  | "breaking change"
  | "opinionated/nonessential";

export type FitScore = "strong fit" | "possible fit with adaptation" | "low fit" | "reject";
export type PortLane = "safe" | "risky" | "reject";

export interface UpstreamWatchConfig {
  upstreamRepo: string;
  upstreamRemoteName: string;
  defaultBaseBranch: string;
  stateIssueTitle: string;
  reportOutputDir: string;
  reportTemplatePath: string;
  labels: Record<string, string>;
  classification: {
    categoryKeywords: Record<ChangeCategory, string[]>;
    fitWeights: Record<ChangeCategory, number>;
    strongFitThreshold: number;
    possibleFitThreshold: number;
    maxSafeFiles: number;
    maxSafeInsertions: number;
    maxSafeDeletions: number;
    riskyFileThreshold: number;
  };
  policy: {
    rejectPathPrefixes: string[];
    manualReviewPathPrefixes: string[];
    preferPathPrefixes: string[];
    rejectSubjectKeywords: string[];
    riskySubjectKeywords: string[];
    forceSafeSubjectKeywords: string[];
  };
}

export interface ReleaseRef {
  tag: string;
  name: string;
  body: string;
  htmlUrl: string;
  publishedAt: string;
  isPrerelease: boolean;
}

export interface CommitInsight {
  sha: string;
  shortSha: string;
  subject: string;
  body: string;
  changedFiles: string[];
  insertions: number;
  deletions: number;
  categories: ChangeCategory[];
  fit: FitScore;
  lane: PortLane;
  rationale: string[];
  alreadyInFork: boolean;
  compatibility: "clean" | "conflict" | "unknown";
}

export interface UpstreamState {
  lastReviewedTag?: string;
  lastReviewedAt?: string;
  lastSafePr?: string;
  lastRiskyPr?: string;
}

export interface AnalysisResult {
  release: ReleaseRef;
  previousTag?: string;
  compareUrl?: string;
  releaseNotes: string;
  commits: CommitInsight[];
  safeCandidates: CommitInsight[];
  riskyCandidates: CommitInsight[];
  rejected: CommitInsight[];
  compatibilityFailures: CommitInsight[];
}

interface CompareResponse {
  html_url?: string;
}

function runGit(args: string[], cwd: string): string {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function tryGit(args: string[], cwd: string): { ok: boolean; stdout: string; stderr: string } {
  try {
    return { ok: true, stdout: runGit(args, cwd), stderr: "" };
  } catch (error) {
    const stderr =
      error instanceof Error && "stderr" in error
        ? String((error as { stderr?: string }).stderr ?? "")
        : String(error);
    return { ok: false, stdout: "", stderr };
  }
}

function asOptionalString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export async function loadJsonFile<T>(filePath: string): Promise<T> {
  return JSON.parse(await readFile(filePath, "utf8")) as T;
}

export async function apiRequest<T>(token: string, route: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/vnd.github+json");
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("User-Agent", "openclaw-upstream-watch");

  const response = await fetch(`https://api.github.com${route}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub API ${route} failed (${response.status}): ${body}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function getLatestRelease(token: string, upstreamRepo: string): Promise<ReleaseRef> {
  const release = await apiRequest<Record<string, unknown>>(
    token,
    `/repos/${upstreamRepo}/releases/latest`,
  );
  return {
    tag: asOptionalString(release.tag_name),
    name: asOptionalString(release.name) || asOptionalString(release.tag_name),
    body: asOptionalString(release.body),
    htmlUrl: asOptionalString(release.html_url),
    publishedAt: asOptionalString(release.published_at),
    isPrerelease: Boolean(release.prerelease),
  };
}

export async function getRepoDefaultBranch(token: string, repo: string): Promise<string> {
  const payload = await apiRequest<Record<string, unknown>>(token, `/repos/${repo}`);
  return asOptionalString(payload.default_branch) || "main";
}

export async function getCompareUrl(
  token: string,
  repo: string,
  previousTag: string,
  currentTag: string,
): Promise<string | undefined> {
  if (!previousTag) {
    return undefined;
  }
  const payload = await apiRequest<CompareResponse>(
    token,
    `/repos/${repo}/compare/${encodeURIComponent(previousTag)}...${encodeURIComponent(currentTag)}`,
  );
  return payload.html_url;
}

export function ensureUpstreamRemote(
  repoRoot: string,
  remoteName: string,
  upstreamRepo: string,
): void {
  const remoteUrl = `https://github.com/${upstreamRepo}.git`;
  const existing = tryGit(["remote", "get-url", remoteName], repoRoot);
  if (!existing.ok) {
    runGit(["remote", "add", remoteName, remoteUrl], repoRoot);
  } else if (existing.stdout !== remoteUrl) {
    runGit(["remote", "set-url", remoteName, remoteUrl], repoRoot);
  }
  runGit(["fetch", remoteName, "--tags", "--force"], repoRoot);
}

export function getOrderedTags(repoRoot: string): string[] {
  const out = runGit(["tag", "--list", "--sort=-creatordate"], repoRoot);
  return out
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function getPreviousTag(
  tags: string[],
  currentTag: string,
  lastReviewedTag?: string,
): string | undefined {
  if (lastReviewedTag && lastReviewedTag !== currentTag) {
    return lastReviewedTag;
  }
  const index = tags.indexOf(currentTag);
  if (index < 0) {
    return undefined;
  }
  return tags[index + 1];
}

export function getCommitShasInRange(
  repoRoot: string,
  previousTag: string | undefined,
  currentTag: string,
): string[] {
  const range = previousTag ? `${previousTag}..${currentTag}` : currentTag;
  const out = runGit(["log", "--reverse", "--format=%H", range], repoRoot);
  return out
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function getCommitDetails(
  repoRoot: string,
  sha: string,
): Omit<
  CommitInsight,
  "categories" | "fit" | "lane" | "rationale" | "alreadyInFork" | "compatibility"
> {
  const subject = runGit(["show", "-s", "--format=%s", sha], repoRoot);
  const body = runGit(["show", "-s", "--format=%b", sha], repoRoot);
  const changedFilesOut = runGit(["show", "--format=", "--name-only", sha], repoRoot);
  const numstatOut = runGit(["show", "--format=", "--numstat", sha], repoRoot);
  const changedFiles = changedFilesOut
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  let insertions = 0;
  let deletions = 0;
  for (const line of numstatOut.split("\n")) {
    const [addRaw, delRaw] = line.split("\t");
    insertions += Number.parseInt(addRaw ?? "0", 10) || 0;
    deletions += Number.parseInt(delRaw ?? "0", 10) || 0;
  }

  return {
    sha,
    shortSha: sha.slice(0, 7),
    subject,
    body,
    changedFiles,
    insertions,
    deletions,
  };
}

export function isAncestor(repoRoot: string, sha: string, ref = "HEAD"): boolean {
  return tryGit(["merge-base", "--is-ancestor", sha, ref], repoRoot).ok;
}

function includesAny(value: string, needles: string[]): boolean {
  const lowered = value.toLowerCase();
  return needles.some((needle) => lowered.includes(needle.toLowerCase()));
}

function classifyCategories(
  config: UpstreamWatchConfig,
  subject: string,
  body: string,
  changedFiles: string[],
): ChangeCategory[] {
  const haystack = `${subject}\n${body}\n${changedFiles.join("\n")}`.toLowerCase();
  const categories = (
    Object.entries(config.classification.categoryKeywords) as Array<[ChangeCategory, string[]]>
  )
    .filter(([, keywords]) => keywords.some((keyword) => haystack.includes(keyword.toLowerCase())))
    .map(([category]) => category);

  if (categories.length === 0) {
    categories.push("opinionated/nonessential");
  }

  return Array.from(new Set(categories));
}

export function scoreCommit(
  config: UpstreamWatchConfig,
  commit: Omit<
    CommitInsight,
    "categories" | "fit" | "lane" | "rationale" | "alreadyInFork" | "compatibility"
  >,
): Pick<CommitInsight, "categories" | "fit" | "lane" | "rationale"> {
  const categories = classifyCategories(config, commit.subject, commit.body, commit.changedFiles);
  let score = categories.reduce(
    (sum, category) => sum + (config.classification.fitWeights[category] ?? 0),
    0,
  );
  const rationale: string[] = [];

  const rejectedPaths = commit.changedFiles.filter((file) =>
    config.policy.rejectPathPrefixes.some((prefix) => file.startsWith(prefix)),
  );
  if (rejectedPaths.length > 0) {
    rationale.push(`Rejected by path policy: ${rejectedPaths.slice(0, 5).join(", ")}`);
    return { categories, fit: "reject", lane: "reject", rationale };
  }

  const manualPaths = commit.changedFiles.filter((file) =>
    config.policy.manualReviewPathPrefixes.some((prefix) => file.startsWith(prefix)),
  );
  if (manualPaths.length > 0) {
    score -= 2;
    rationale.push(`Touches manual-review paths: ${manualPaths.slice(0, 5).join(", ")}`);
  }

  if (
    includesAny(commit.subject, config.policy.rejectSubjectKeywords) ||
    categories.includes("breaking change")
  ) {
    rationale.push("Rejected by breaking or policy keyword.");
    return { categories, fit: "reject", lane: "reject", rationale };
  }

  if (
    config.policy.preferPathPrefixes.some((prefix) =>
      commit.changedFiles.some((file) => file.startsWith(prefix)),
    )
  ) {
    score += 2;
    rationale.push("Touches preferred low-risk paths.");
  }

  if (includesAny(commit.subject, config.policy.forceSafeSubjectKeywords)) {
    score += 2;
    rationale.push("Matched force-safe subject keyword.");
  }

  if (includesAny(commit.subject, config.policy.riskySubjectKeywords)) {
    score -= 3;
    rationale.push("Matched risky subject keyword.");
  }

  if (commit.changedFiles.length > config.classification.riskyFileThreshold) {
    score -= 3;
    rationale.push(`Large file spread (${commit.changedFiles.length} files).`);
  }

  if (
    commit.insertions > config.classification.maxSafeInsertions ||
    commit.deletions > config.classification.maxSafeDeletions
  ) {
    score -= 2;
    rationale.push(`Large patch size (+${commit.insertions}/-${commit.deletions}).`);
  }

  const safeShape =
    commit.changedFiles.length <= config.classification.maxSafeFiles &&
    commit.insertions <= config.classification.maxSafeInsertions &&
    commit.deletions <= config.classification.maxSafeDeletions;

  const safeIntent = categories.some((category) =>
    ["security", "bug fix", "reliability", "performance", "cost efficiency"].includes(category),
  );
  const riskyIntent = categories.some((category) =>
    ["developer experience", "UI/dashboard", "opinionated/nonessential"].includes(category),
  );

  if (score >= config.classification.strongFitThreshold && safeShape && safeIntent) {
    return { categories, fit: "strong fit", lane: "safe", rationale };
  }

  if (
    score >= config.classification.possibleFitThreshold &&
    !categories.includes("breaking change")
  ) {
    return {
      categories,
      fit: "possible fit with adaptation",
      lane: riskyIntent ? "risky" : "safe",
      rationale,
    };
  }

  if (score > 0) {
    return { categories, fit: "low fit", lane: "risky", rationale };
  }

  return { categories, fit: "reject", lane: "reject", rationale };
}

export async function detectCompatibility(
  repoRoot: string,
  commits: CommitInsight[],
): Promise<Map<string, CommitInsight["compatibility"]>> {
  const tmpRoot = await mkdtemp(path.join(os.tmpdir(), "openclaw-upstream-watch-"));
  const statuses = new Map<string, CommitInsight["compatibility"]>();

  try {
    runGit(["worktree", "add", "--detach", tmpRoot, "HEAD"], repoRoot);
    for (const commit of commits) {
      const result = tryGit(["cherry-pick", "--no-commit", commit.sha], tmpRoot);
      if (result.ok) {
        statuses.set(commit.sha, "clean");
        runGit(["reset", "--hard", "HEAD"], tmpRoot);
      } else if (
        result.stderr.includes("after resolving the conflicts") ||
        result.stderr.includes("could not apply")
      ) {
        statuses.set(commit.sha, "conflict");
        tryGit(["cherry-pick", "--abort"], tmpRoot);
        runGit(["reset", "--hard", "HEAD"], tmpRoot);
      } else {
        statuses.set(commit.sha, "unknown");
        tryGit(["cherry-pick", "--abort"], tmpRoot);
        runGit(["reset", "--hard", "HEAD"], tmpRoot);
      }
    }
  } finally {
    tryGit(["worktree", "remove", "--force", tmpRoot], repoRoot);
    await rm(tmpRoot, { recursive: true, force: true });
  }

  return statuses;
}

export function renderReport(template: string, analysis: AnalysisResult): string {
  const safeRows =
    analysis.safeCandidates.length > 0
      ? analysis.safeCandidates
          .map(
            (commit) =>
              `- ${commit.shortSha} ${commit.subject} (${commit.fit}, ${commit.compatibility})`,
          )
          .join("\n")
      : "- None";
  const riskyRows =
    analysis.riskyCandidates.length > 0
      ? analysis.riskyCandidates
          .map(
            (commit) =>
              `- ${commit.shortSha} ${commit.subject} (${commit.fit}, ${commit.compatibility})`,
          )
          .join("\n")
      : "- None";
  const rejectedRows =
    analysis.rejected.length > 0
      ? analysis.rejected
          .map(
            (commit) =>
              `- ${commit.shortSha} ${commit.subject} (${commit.rationale.join("; ") || "rejected"})`,
          )
          .join("\n")
      : "- None";
  const commitRows = analysis.commits
    .map((commit) =>
      [
        `| ${commit.shortSha} | ${commit.subject.replaceAll("|", "\\|")} | ${commit.categories.join(", ")} | ${commit.fit} | ${commit.compatibility} | ${commit.lane} |`,
      ].join(""),
    )
    .join("\n");

  return template
    .replaceAll("{{UPSTREAM_RELEASE}}", `${analysis.release.tag} (${analysis.release.name})`)
    .replaceAll("{{UPSTREAM_RELEASE_URL}}", analysis.release.htmlUrl)
    .replaceAll("{{PREVIOUS_TAG}}", analysis.previousTag ?? "none")
    .replaceAll("{{COMPARE_URL}}", analysis.compareUrl ?? "n/a")
    .replaceAll("{{SAFE_IMPORTS}}", safeRows)
    .replaceAll("{{RISKY_IMPORTS}}", riskyRows)
    .replaceAll("{{EXCLUDED_ITEMS}}", rejectedRows)
    .replaceAll(
      "{{RISKS}}",
      analysis.compatibilityFailures.length > 0
        ? analysis.compatibilityFailures
            .map((commit) => `- ${commit.shortSha} ${commit.subject} (${commit.compatibility})`)
            .join("\n")
        : "- No unresolved compatibility blockers.",
    )
    .replaceAll(
      "{{TESTS_RUN}}",
      "- Commit classification\n- Cherry-pick compatibility dry-run\n- Report generation",
    )
    .replaceAll(
      "{{ROLLBACK_NOTES}}",
      "- PR branches only. No merge to main. Close PR and delete branch to roll back the proposed port.",
    )
    .replaceAll(
      "{{RELEASE_NOTES}}",
      analysis.releaseNotes || "No upstream release notes were published.",
    )
    .replaceAll("{{COMMIT_TABLE}}", commitRows || "| n/a | n/a | n/a | n/a | n/a | n/a |")
    .replaceAll("{{ACTION_PLAN}}", buildActionPlan(analysis));
}

function buildActionPlan(analysis: AnalysisResult): string {
  const lines: string[] = [];
  if (analysis.safeCandidates.length > 0) {
    lines.push(
      `1. Open or update a safe-port PR with ${analysis.safeCandidates.length} clean cherry-pick candidate(s).`,
    );
  }
  if (analysis.riskyCandidates.length > 0) {
    lines.push(
      `${lines.length + 1}. Open or update a draft risky-port PR with ${analysis.riskyCandidates.length} optional candidate(s).`,
    );
  }
  if (analysis.rejected.length > 0) {
    lines.push(`${lines.length + 1}. Keep rejected commits out of the fork unless policy changes.`);
  }
  if (analysis.compatibilityFailures.length > 0) {
    lines.push(
      `${lines.length + 1}. Stop and request human review for ${analysis.compatibilityFailures.length} compatibility blocker(s).`,
    );
  }
  return lines.length > 0
    ? lines.join("\n")
    : "1. No worthwhile changes detected. Keep the fork unchanged.";
}

export async function writeReport(
  outputDir: string,
  releaseTag: string,
  content: string,
): Promise<string> {
  await mkdir(outputDir, { recursive: true });
  const safeTag = releaseTag.replaceAll(/[^a-zA-Z0-9._-]/g, "-");
  const filePath = path.join(outputDir, `${safeTag}.md`);
  const latestPath = path.join(outputDir, "latest.md");
  await writeFile(filePath, content, "utf8");
  await writeFile(latestPath, content, "utf8");
  return filePath;
}

export async function loadTemplate(templatePath: string): Promise<string> {
  return readFile(templatePath, "utf8");
}
