# GitHub Notification Triage Playbook

Use this playbook to classify GitHub notification emails and route pull requests quickly without losing critical reviews.

## Decision classes

Choose exactly one outcome per email:

1. Archive
2. FYI
3. Human review
4. Codex review
5. Both human + Codex
6. Urgent escalation

## Extraction checklist

Capture the following before deciding:

- Repository
- PR number and title
- Author
- Requested reviewers
- Labels
- Branch
- CI or test status (if present)
- Mergeability and blockers (if present)
- Mentioned files, directories, or components
- Notification type (new PR, review request, comment, CI failure, merge, close, general)
- Urgency indicators (release, hotfix, incident, security, customer impact, production, payment, auth, migration, compliance)

## Routing rules

### Send to human review

Use human review for:

- authn or authz, billing, payments, security, privacy, PII, compliance, legal
- infra, data model changes, migrations, public API or SDK updates
- architecture changes, reliability paths, observability or deployment behavior
- large or ambiguous PRs that need product judgment
- unknown contributors touching sensitive systems
- nontrivial CI failures, merge conflicts, rollback risk, or release implications

### Send to Codex review

Use Codex for low-risk, narrow scope, and mechanically checkable work:

- docs, tests, lint, typing, small refactors, CI cleanup
- localized bug fixes with low blast radius
- no obvious security, privacy, compliance, billing, or architecture sensitivity

Default comment:

```text
@codex review
```

Focused variants:

```text
@codex review for security regressions
@codex review for test gaps
@codex review for CI failures
```

### Send to both human + Codex

Use both when Codex can reduce review load, but final sign-off should remain with engineering:

- medium-risk PRs
- technically tricky but not policy-sensitive changes
- moderate scope where an early automated pass helps

### Urgent escalation

Escalate when email signals:

- active incident or outage
- security event or potential data exposure
- release-blocking failure
- hotfix with customer impact

## Action policy

- Draft actions when confidence is below 85 percent.
- Never route sensitive or compliance-heavy reviews to Codex alone.
- Prefer both over overconfidence.
- Archive FYI or low-value noise unless explicitly requested or directly mentioned.

## Output template

Use this exact structure per email:

```text
Decision: <Archive | FYI | Human review | Codex review | Both human + Codex | Urgent escalation>
Confidence: <0-100>
Reasoning: <brief, concrete explanation>
Risk level: <low|medium|high|urgent>
Recommended owner: <person/team/Codex/none>
Recommended next action: <archive | draft human email | trigger Codex review | both | escalate>
Draft email or GitHub comment:
<content>
Inbox handling:
<label, archive, keep unread, or star>

Executive summary: <one line for inbox preview>
```

## Human-review email template

```text
Subject: [PR Review Needed] <repo> #<pr-number> <title>

<2-4 sentence summary of PR and current status.>

Reason this requires human review: <specific risk or judgment call>.
Suggested reviewer/team: <owner>.
Urgency: <low|normal|high|urgent>.
```

## Both human + Codex template

```text
Subject: [PR Review Needed] <repo> #<pr-number> <title>

<2-4 sentence summary of PR and status.>

Reason this requires human review: <specific risk/judgment>.
Suggested reviewer/team: <owner>.
Urgency: <low|normal|high|urgent>.

Run Codex first-pass review:
@codex review

After Codex responds, human reviewer should verify:
- business logic intent
- risk acceptance and rollout/rollback safety
- unresolved comments from Codex and CI signal
```
