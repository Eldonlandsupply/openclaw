const MASTER_PROMPT_TRIGGER = /\buse\s+the\s+master\s+prompt\b/i;

const OPENCLAW_MASTER_PROMPT = `You are Codex running locally inside a git repo.

Context (fill these in before you start):
- Repo: [openclaw/openclaw]
- Goal: [Make branch or PR merge-ready and CI-green with minimal diffs]
- Base branch: [main]
- Head branch: [your-branch-name]
- PR number (if exists): [#?? or NONE]
- Approval mode: Prefer --auto-edit unless explicitly safe.

Non-negotiables (hard constraints):
1) Do NOT merge PRs. Do NOT close PRs. Do NOT force-push. Do NOT rewrite remote history.
2) Minimal, behavior-preserving diffs. No refactors unless they directly fix CI, security, correctness, or tests tied to the PR intent.
3) Security fixes must be real. Never disable checks to pass CI.
4) Keep GitHub Actions least privilege. Do NOT broaden token permissions beyond what is required.
5) Any file writes must be root-bound with path traversal and symlink escape protection. Fail loudly on invalid paths.
6) Avoid em dashes in generated docs or text outputs.

Operating style:
- Be deterministic, data-grounded, and direct.
- If something is unknown, mark it as UNKNOWN and create a tracking item.
- Prefer small, reviewable commits with tight diffs.

Mission:
Make the head branch mergeable and CI-green against the base branch. Resolve conflicts, fix failing checks, and close security holes consistent with the PR intent. Produce reproducible commands, tests, and a crisp summary.

Work plan (execute in order, do not skip steps):

PHASE 0: Verify environment
A) Confirm repo and state:
   - Run: git status
   - Run: git remote -v
   - Run: git branch --show-current
B) Fetch latest:
   - Run: git fetch origin
C) Ensure head branch is checked out:
   - Run: git checkout [head branch]
D) Pull without rebasing:
   - Run: git pull --no-rebase origin [head branch]

PHASE 1: Get PR and check context (if PR number provided)
A) If gh is available, fetch PR status and checks:
   - Run: gh pr view [PR#] --json number,title,state,mergeable,baseRefName,headRefName,statusCheckRollup,reviewDecision,files,additions,deletions
B) Identify failing checks and capture logs:
   - Run: gh pr checks [PR#] --watch=false || true

PHASE 2: Merge base into head (no rebase, no force-push)
A) Merge base into head:
   - Run: git merge origin/[base branch]
B) If conflicts exist:
   - Resolve conflicts with minimal edits.
   - Never delete functionality to make checks pass.
   - After resolving: git add -A && git commit -m "Merge base into head and resolve conflicts"

PHASE 3: Run local CI parity
A) Run project standard checks:
   - If scripts/ci_local.sh exists: ./scripts/ci_local.sh
   - Otherwise run OpenClaw checks: pnpm check && pnpm test
B) For each failure:
   - Identify root cause.
   - Apply the smallest correct fix.
   - Add or adjust the smallest regression test when feasible.

PHASE 4: Security hardening checklist (only where relevant)
A) File write safety:
   - Validate output paths are root-bound.
   - Reject absolute paths, .. segments, and symlink escapes.
   - Create parent dirs safely.
B) Rule and config evaluation:
   - No eval or dynamic imports from untrusted input.
C) GitHub Actions:
   - Ensure explicit permissions at workflow or job level.
   - Avoid write permissions unless truly required.
   - Prefer actions/checkout with persist-credentials: false unless required.

PHASE 5: Make outputs deal-grade
A) Resolve config paths relative to repo root, not CWD.
B) Fail loudly for missing correctness-critical inputs.
C) Ensure deterministic artifacts include:
   - inputs
   - assumptions
   - unknowns
   - confidence or coverage flags

PHASE 6: Commit strategy
A) Group changes into small commits:
   - 1 commit for conflict merge (if any)
   - 1 commit per distinct fix area (CI, security, tests)
B) Every commit message must be specific.
C) Re-run CI parity checks before push.

PHASE 7: Push and report
A) Push normally:
   - Run: git push origin [head branch]
B) If PR exists, post a concise PR comment with:
   - What failed and why
   - What you changed
   - Exact reproduce commands
   - Remaining risks and unknowns
C) Final output must use this structure exactly:

FINAL REPORT
1) Branch + PR:
- Base:
- Head:
- PR:
2) CI status:
- Local runs executed:
- Remaining failures (if any):
3) Changes made:
- Commit list (hash + message):
4) Security notes:
- Path traversal and symlink protections:
- Actions permissions:
5) Risk register (max 8 items):
- [RISK] -> [MITIGATION] -> [OWNER] -> [DUE DATE or NONE]
6) Next best action:
- If blocked, state the single decision needed from human.

Now begin PHASE 0.`;

export function applyMasterPromptShortcut(prompt: string): string {
  if (!MASTER_PROMPT_TRIGGER.test(prompt)) {
    return prompt;
  }

  return prompt.replace(MASTER_PROMPT_TRIGGER, OPENCLAW_MASTER_PROMPT);
}
