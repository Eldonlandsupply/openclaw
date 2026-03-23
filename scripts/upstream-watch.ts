import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  apiRequest,
  detectCompatibility,
  ensureUpstreamRemote,
  getCommitDetails,
  getCommitShasInRange,
  getCompareUrl,
  getLatestRelease,
  getOrderedTags,
  getPreviousTag,
  getRepoDefaultBranch,
  isAncestor,
  loadJsonFile,
  loadTemplate,
  renderReport,
  scoreCommit,
  writeReport,
  type AnalysisResult,
  type CommitInsight,
  type UpstreamState,
  type UpstreamWatchConfig,
} from "../src/infra/upstream-watch.ts";

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

function getArg(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

async function getOrCreateStateIssue(
  token: string,
  repo: string,
  title: string,
  labels: string[],
): Promise<{ number: number; body: string }> {
  const issues = await apiRequest<Array<Record<string, unknown>>>(
    token,
    `/repos/${repo}/issues?state=all&per_page=100`,
  );
  const issue = issues.find((item) => !item.pull_request && item.title === title);
  const initialBody = [
    "<!-- upstream-watch-state -->",
    "```json",
    JSON.stringify({}, null, 2),
    "```",
  ].join("\n");

  if (issue) {
    return { number: Number(issue.number), body: asOptionalString(issue.body) };
  }

  const created = await apiRequest<Record<string, unknown>>(token, `/repos/${repo}/issues`, {
    method: "POST",
    body: JSON.stringify({ title, body: initialBody, labels }),
  });

  return { number: Number(created.number), body: initialBody };
}

function parseState(body: string): UpstreamState {
  const match = body.match(/<!-- upstream-watch-state -->\s*```json\s*([\s\S]*?)\s*```/);
  if (!match) {
    return {};
  }
  return JSON.parse(match[1]) as UpstreamState;
}

async function saveState(
  token: string,
  repo: string,
  issueNumber: number,
  state: UpstreamState,
): Promise<void> {
  const body = [
    "<!-- upstream-watch-state -->",
    "```json",
    JSON.stringify(state, null, 2),
    "```",
  ].join("\n");
  await apiRequest(token, `/repos/${repo}/issues/${issueNumber}`, {
    method: "PATCH",
    body: JSON.stringify({ body }),
  });
}

async function ensureLabel(
  token: string,
  repo: string,
  name: string,
  description: string,
  color: string,
): Promise<void> {
  const existing = await apiRequest<Array<Record<string, unknown>>>(
    token,
    `/repos/${repo}/labels?per_page=100`,
  );
  const label = existing.find((item) => item.name === name);
  if (label) {
    return;
  }
  await apiRequest(token, `/repos/${repo}/labels`, {
    method: "POST",
    body: JSON.stringify({ name, description, color }),
  });
}

function loadConfig(repoRoot: string): Promise<UpstreamWatchConfig> {
  return loadJsonFile<UpstreamWatchConfig>(
    path.join(repoRoot, ".github/upstream-watch/config.json"),
  );
}

async function ensureLabels(
  token: string,
  repo: string,
  config: UpstreamWatchConfig,
): Promise<void> {
  await ensureLabel(
    token,
    repo,
    config.labels["upstream-sync"],
    "PR or issue created by upstream watch automation",
    "1d76db",
  );
  await ensureLabel(
    token,
    repo,
    config.labels["safe-port"],
    "High-confidence upstream port candidate",
    "0e8a16",
  );
  await ensureLabel(
    token,
    repo,
    config.labels["needs-review"],
    "Needs human compatibility review",
    "fbca04",
  );
  await ensureLabel(
    token,
    repo,
    config.labels["breaking-risk"],
    "Breaking-risk upstream change",
    "d73a4a",
  );
  await ensureLabel(
    token,
    repo,
    config.labels["rejected-by-policy"],
    "Rejected by fork policy",
    "6f42c1",
  );
}

async function createAnalysis(
  repoRoot: string,
  token: string,
  config: UpstreamWatchConfig,
  state: UpstreamState,
  forcedTag?: string,
): Promise<AnalysisResult> {
  ensureUpstreamRemote(repoRoot, config.upstreamRemoteName, config.upstreamRepo);
  const latestRelease = await getLatestRelease(token, config.upstreamRepo);
  const release = forcedTag ? { ...latestRelease, tag: forcedTag, name: forcedTag } : latestRelease;
  const orderedTags = getOrderedTags(repoRoot);
  if (!orderedTags.includes(release.tag)) {
    throw new Error(`Upstream tag ${release.tag} was not fetched locally.`);
  }

  const previousTag = getPreviousTag(orderedTags, release.tag, state.lastReviewedTag);
  const compareUrl = previousTag
    ? await getCompareUrl(token, config.upstreamRepo, previousTag, release.tag)
    : undefined;
  const commitShas = getCommitShasInRange(repoRoot, previousTag, release.tag);
  const commitsBase = commitShas.map((sha) => getCommitDetails(repoRoot, sha));
  const prelim: CommitInsight[] = commitsBase.map((commit) => {
    const scored = scoreCommit(config, commit);
    return {
      ...commit,
      ...scored,
      alreadyInFork: isAncestor(repoRoot, commit.sha, "HEAD"),
      compatibility: "unknown",
    };
  });

  const candidates = prelim.filter((commit) => commit.fit !== "reject" && !commit.alreadyInFork);
  const compatibilityMap = await detectCompatibility(repoRoot, candidates);
  const commits = prelim.map((commit) => ({
    ...commit,
    compatibility: compatibilityMap.get(commit.sha) ?? (commit.alreadyInFork ? "clean" : "unknown"),
  }));
  const worthwhile = commits.filter(
    (commit) =>
      (commit.fit === "strong fit" || commit.fit === "possible fit with adaptation") &&
      !commit.alreadyInFork,
  );
  const compatibilityFailures = worthwhile.filter((commit) => commit.compatibility !== "clean");

  return {
    release,
    previousTag,
    compareUrl,
    releaseNotes: release.body,
    commits,
    safeCandidates: commits.filter(
      (commit) =>
        commit.lane === "safe" &&
        commit.fit === "strong fit" &&
        commit.compatibility === "clean" &&
        !commit.alreadyInFork,
    ),
    riskyCandidates: commits.filter(
      (commit) =>
        commit.lane === "risky" &&
        commit.fit === "possible fit with adaptation" &&
        commit.compatibility === "clean" &&
        !commit.alreadyInFork,
    ),
    rejected: commits.filter(
      (commit) => commit.fit === "reject" || commit.fit === "low fit" || commit.alreadyInFork,
    ),
    compatibilityFailures,
  };
}

function branchNameForLane(tag: string, lane: "safe" | "risky"): string {
  return `bot/upstream-${lane}-${tag.replaceAll(/[^a-zA-Z0-9._-]/g, "-")}`;
}

async function pushLaneBranch(
  repoRoot: string,
  baseBranch: string,
  lane: "safe" | "risky",
  commits: CommitInsight[],
): Promise<string> {
  const actualBranch = branchNameForLane(process.env.UPSTREAM_WATCH_RELEASE_TAG ?? "release", lane);
  const originalBranch = runGit(["branch", "--show-current"], repoRoot);
  runGit(["fetch", "origin", baseBranch], repoRoot);
  const remoteBranch = tryGit(["ls-remote", "--heads", "origin", actualBranch], repoRoot).stdout;
  if (remoteBranch) {
    runGit(["checkout", "-B", actualBranch, `origin/${actualBranch}`], repoRoot);
  } else {
    runGit(["checkout", "-B", actualBranch, `origin/${baseBranch}`], repoRoot);
  }

  let changed = false;
  for (const commit of commits) {
    if (tryGit(["merge-base", "--is-ancestor", commit.sha, "HEAD"], repoRoot).ok) {
      continue;
    }
    const result = tryGit(["cherry-pick", "-x", commit.sha], repoRoot);
    if (!result.ok) {
      tryGit(["cherry-pick", "--abort"], repoRoot);
      throw new Error(`Failed to cherry-pick ${commit.sha} into ${actualBranch}: ${result.stderr}`);
    }
    changed = true;
  }

  if (changed || !remoteBranch) {
    runGit(["push", "-u", "origin", actualBranch], repoRoot);
  }
  runGit(["checkout", originalBranch], repoRoot);
  return actualBranch;
}

async function upsertPullRequest(
  token: string,
  repo: string,
  base: string,
  head: string,
  title: string,
  body: string,
  labels: string[],
  draft: boolean,
): Promise<string> {
  const prs = await apiRequest<Array<Record<string, unknown>>>(
    token,
    `/repos/${repo}/pulls?state=open&head=${encodeURIComponent(`${repo.split("/")[0]}:${head}`)}`,
  );
  let prNumber: number;
  let prUrl: string;

  if (prs.length > 0) {
    const pr = prs[0];
    prNumber = Number(pr.number);
    await apiRequest(token, `/repos/${repo}/pulls/${prNumber}`, {
      method: "PATCH",
      body: JSON.stringify({ title, body }),
    });
    prUrl = asOptionalString(pr.html_url);
  } else {
    const created = await apiRequest<Record<string, unknown>>(token, `/repos/${repo}/pulls`, {
      method: "POST",
      body: JSON.stringify({ title, body, head, base, draft }),
    });
    prNumber = Number(created.number);
    prUrl = asOptionalString(created.html_url);
  }

  await apiRequest(token, `/repos/${repo}/issues/${prNumber}/labels`, {
    method: "POST",
    body: JSON.stringify({ labels }),
  });
  return prUrl;
}

function labelsForLane(
  config: UpstreamWatchConfig,
  analysis: AnalysisResult,
  lane: "safe" | "risky",
  commits: CommitInsight[],
): string[] {
  const labels = [config.labels["upstream-sync"]];
  if (lane === "safe") {
    labels.push(config.labels["safe-port"]);
  } else {
    labels.push(config.labels["needs-review"]);
  }
  if (analysis.rejected.some((commit) => commit.categories.includes("breaking change"))) {
    labels.push(config.labels["breaking-risk"]);
  }
  if (analysis.rejected.some((commit) => commit.fit === "reject")) {
    labels.push(config.labels["rejected-by-policy"]);
  }
  if (commits.some((commit) => commit.compatibility !== "clean")) {
    labels.push(config.labels["needs-review"]);
  }
  return Array.from(new Set(labels));
}

function buildPrBody(
  analysis: AnalysisResult,
  lane: "safe" | "risky",
  commits: CommitInsight[],
): string {
  const topRecommended = commits
    .map((commit) => `- ${commit.shortSha} ${commit.subject}`)
    .join("\n");
  const excluded =
    analysis.rejected
      .slice(0, 8)
      .map((commit) => `- ${commit.shortSha} ${commit.subject}`)
      .join("\n") || "- None";
  const risks =
    lane === "safe"
      ? "- Low. All selected commits passed cherry-pick dry-run against the fork head."
      : "- Medium. Commits are clean cherry-picks, but they need human review for policy fit and downstream behavior.";

  return [
    `## Upstream release reviewed`,
    `- ${analysis.release.tag} (${analysis.release.htmlUrl})`,
    "",
    `## Top recommended imports`,
    topRecommended || "- None",
    "",
    `## Excluded items`,
    excluded,
    "",
    `## Risks`,
    risks,
    "",
    `## Tests run`,
    "- Commit classification",
    "- Cherry-pick compatibility dry-run",
    "- Targeted automation validation",
    "",
    `## Rollback notes`,
    "- Close this PR if the import is not wanted.",
    "- Delete the bot branch to remove the proposal.",
  ].join("\n");
}

async function main(): Promise<void> {
  const repoRoot = runGit(["rev-parse", "--show-toplevel"], process.cwd());
  const token = process.env.GITHUB_TOKEN;
  const currentRepo = process.env.GITHUB_REPOSITORY;
  if (!token || !currentRepo) {
    throw new Error("GITHUB_TOKEN and GITHUB_REPOSITORY are required.");
  }

  const config = await loadConfig(repoRoot);
  const baseBranch =
    process.env.UPSTREAM_WATCH_BASE_BRANCH ||
    (await getRepoDefaultBranch(token, currentRepo)) ||
    config.defaultBaseBranch;
  const forcedTag = getArg("--release-tag");
  const dryRun = process.argv.includes("--dry-run");
  const createPrs = !process.argv.includes("--no-pr");
  const stateIssue = await getOrCreateStateIssue(token, currentRepo, config.stateIssueTitle, [
    config.labels["upstream-sync"],
  ]);
  const state = parseState(stateIssue.body);
  const analysis = await createAnalysis(repoRoot, token, config, state, forcedTag);
  process.env.UPSTREAM_WATCH_RELEASE_TAG = analysis.release.tag;

  const template = await loadTemplate(path.join(repoRoot, config.reportTemplatePath));
  const report = renderReport(template, analysis);
  const reportPath = await writeReport(
    path.join(repoRoot, config.reportOutputDir),
    analysis.release.tag,
    report,
  );
  await mkdir(path.join(repoRoot, ".artifacts/upstream-watch"), { recursive: true });
  await writeFile(
    path.join(repoRoot, ".artifacts/upstream-watch/analysis.json"),
    JSON.stringify(analysis, null, 2),
  );

  if (!dryRun) {
    await ensureLabels(token, currentRepo, config);
  }

  if (state.lastReviewedTag === analysis.release.tag && !forcedTag) {
    console.log(`No new upstream release. Last reviewed tag remains ${analysis.release.tag}.`);
    console.log(`Report: ${reportPath}`);
    return;
  }

  if (analysis.compatibilityFailures.length > 0) {
    console.error(
      `Compatibility could not be determined cleanly for ${analysis.compatibilityFailures.length} worthwhile commit(s).`,
    );
    console.error(`Report: ${reportPath}`);
    process.exitCode = 1;
    return;
  }

  let safePrUrl: string | undefined;
  let riskyPrUrl: string | undefined;
  if (!dryRun && createPrs) {
    if (analysis.safeCandidates.length > 0) {
      const safeBranch = await pushLaneBranch(
        repoRoot,
        baseBranch,
        "safe",
        analysis.safeCandidates,
      );
      safePrUrl = await upsertPullRequest(
        token,
        currentRepo,
        baseBranch,
        safeBranch,
        `Upstream watch: safe ports from ${analysis.release.tag}`,
        buildPrBody(analysis, "safe", analysis.safeCandidates),
        labelsForLane(config, analysis, "safe", analysis.safeCandidates),
        false,
      );
    }
    if (analysis.riskyCandidates.length > 0) {
      const riskyBranch = await pushLaneBranch(
        repoRoot,
        baseBranch,
        "risky",
        analysis.riskyCandidates,
      );
      riskyPrUrl = await upsertPullRequest(
        token,
        currentRepo,
        baseBranch,
        riskyBranch,
        `Upstream watch: optional ports from ${analysis.release.tag}`,
        buildPrBody(analysis, "risky", analysis.riskyCandidates),
        labelsForLane(config, analysis, "risky", analysis.riskyCandidates),
        true,
      );
    }
  }

  if (!dryRun) {
    await saveState(token, currentRepo, stateIssue.number, {
      lastReviewedTag: analysis.release.tag,
      lastReviewedAt: new Date().toISOString(),
      lastSafePr: safePrUrl,
      lastRiskyPr: riskyPrUrl,
    });
  }

  console.log(`Report: ${reportPath}`);
  if (safePrUrl) {
    console.log(`Safe PR: ${safePrUrl}`);
  }
  if (riskyPrUrl) {
    console.log(`Risky PR: ${riskyPrUrl}`);
  }
  if (!safePrUrl && !riskyPrUrl) {
    console.log("No worthwhile changes. No PR created.");
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
