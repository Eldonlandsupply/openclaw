#!/usr/bin/env python3
"""Refresh and validate the CTO control-center state for directly accessible repositories.

This script only uses local filesystem and git metadata. Remote PR and CI state must come
from a real direct integration. When that integration is unavailable, the script records
`MISSING INTEGRATION` or `UNKNOWN` instead of guessing.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CTO_ROOT = ROOT / "agents" / "cto"
CONFIG = CTO_ROOT / "config" / "standards.yaml"
REGISTRY = CTO_ROOT / "repos" / "registry.yaml"
REPORTS_DIR = CTO_ROOT / "reports"
STATE_DIR = CTO_ROOT / "state"
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
HEALTH_PATH = CTO_ROOT / "repos" / "health" / "openclaw.json"
PR_PATH = CTO_ROOT / "repos" / "pr_tracking" / "openclaw.json"
CI_PATH = CTO_ROOT / "repos" / "ci_tracking" / "openclaw.json"
BOOTSTRAP_STATE_PATH = STATE_DIR / "bootstrap_state.json"
RUN_LOG_PATH = STATE_DIR / "last_run.json"
REQUIRED_PATHS = [
    CTO_ROOT / "README.md",
    CONFIG,
    CTO_ROOT / "prompts",
    CTO_ROOT / "playbooks",
    CTO_ROOT / "scripts",
    REPORTS_DIR,
    STATE_DIR,
    REGISTRY,
    CTO_ROOT / "repos" / "health",
    CTO_ROOT / "repos" / "pr_tracking",
    CTO_ROOT / "repos" / "ci_tracking",
]


@dataclass
class GitSnapshot:
    active_branch: str
    default_branch: str
    remotes: list[str]
    has_origin: bool


@dataclass
class ValidationResult:
    missing_paths: list[str]
    missing_registry_fields: list[str]
    workflow_files: list[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def wrap_line(prefix: str, text: str, width: int = 80) -> list[str]:
    return textwrap.wrap(
        f"{prefix}{text}",
        width=width,
        subsequent_indent=" " * len(prefix),
        break_long_words=False,
        break_on_hyphens=False,
    )


def parse_simple_yaml(path: Path) -> dict[str, Any]:
    # The CTO config file is intentionally simple, so lightweight parsing keeps the script dependency-free.
    text = path.read_text().strip()
    current_key: str | None = None
    parsed: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not value:
                parsed[key] = []
                current_key = key
            elif value.startswith("[") and value.endswith("]"):
                parsed[key] = [item.strip() for item in value[1:-1].split(",") if item.strip()]
                current_key = None
            else:
                parsed[key] = value.strip('"')
                current_key = None
        elif current_key and line.lstrip().startswith("-"):
            parsed.setdefault(current_key, []).append(line.split("-", 1)[1].strip())
    return parsed


def git_snapshot() -> GitSnapshot:
    active_branch = run_git("branch", "--show-current") or "UNKNOWN"
    default_branch = run_git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if default_branch.startswith("origin/"):
        default_branch = default_branch.split("/", 1)[1]
    elif not default_branch:
        default_branch = "UNKNOWN"
    remotes_output = run_git("remote", "-v")
    remotes = sorted({line.split()[0] for line in remotes_output.splitlines() if line.strip()})
    return GitSnapshot(
        active_branch=active_branch,
        default_branch=default_branch,
        remotes=remotes,
        has_origin="origin" in remotes,
    )


def validate_control_center() -> ValidationResult:
    missing_paths = [str(path.relative_to(ROOT)) for path in REQUIRED_PATHS if not path.exists()]
    workflow_files = sorted(str(path.relative_to(ROOT)) for path in WORKFLOWS_DIR.glob("*.yml"))

    registry_text = REGISTRY.read_text()
    missing_registry_fields = []
    for token in [
        "name:",
        "owner:",
        "repo:",
        "path:",
        "commands:",
        "ci_workflows:",
        "branch_protection_expectations:",
        "risk_summary:",
    ]:
        if token not in registry_text:
            missing_registry_fields.append(token)

    return ValidationResult(
        missing_paths=missing_paths,
        missing_registry_fields=missing_registry_fields,
        workflow_files=workflow_files,
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_text(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n")


def build_open_failures(git: GitSnapshot, validation: ValidationResult) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if validation.missing_paths:
        failures.append(
            {
                "id": "control_center.structure_missing",
                "severity": "high",
                "summary": "Required CTO control-center paths are missing.",
                "next_action": f"Restore the missing paths: {', '.join(validation.missing_paths)}.",
            }
        )
    if validation.missing_registry_fields:
        failures.append(
            {
                "id": "control_center.registry_incomplete",
                "severity": "high",
                "summary": "The CTO repository registry is missing required fields.",
                "next_action": f"Restore required registry fields: {', '.join(validation.missing_registry_fields)}.",
            }
        )
    if not git.has_origin:
        failures.append(
            {
                "id": "integration.github.remote_missing",
                "severity": "medium",
                "summary": "Git remotes are not configured in the local checkout, so upstream PR and CI state cannot be queried directly.",
                "next_action": "Connect the canonical Git remote, then hydrate PR and CI trackers from direct metadata.",
            }
        )
    return failures


def status_for_failures(failures: list[dict[str, str]]) -> str:
    if any(item["severity"] == "high" for item in failures):
        return "RED"
    if failures:
        return "YELLOW"
    return "GREEN"


def refresh() -> list[dict[str, str]]:
    timestamp = utc_now()
    today = date.today().isoformat()
    standards = parse_simple_yaml(CONFIG)
    git = git_snapshot()
    validation = validate_control_center()
    browser_rejection = (
        "Browser automation was rejected because the CTO control center can be audited and refreshed through direct filesystem, git, and CI workflow inspection."
    )
    open_failures = build_open_failures(git, validation)
    repo_status = status_for_failures(open_failures)
    github_integration = "available" if git.has_origin else "MISSING INTEGRATION"

    bootstrap_state = read_json(BOOTSTRAP_STATE_PATH)
    bootstrap_state.update(
        {
            "bootstrapped_at": timestamp,
            "accessible_repositories": [str(ROOT)],
            "github_integration": github_integration,
            "notes": [
                "Bootstrapped from direct filesystem and local git inspection.",
                "Remote PR and CI state stays UNKNOWN until a direct integration is configured.",
            ],
        }
    )
    write_json(BOOTSTRAP_STATE_PATH, bootstrap_state)

    health = read_json(HEALTH_PATH)
    health.update(
        {
            "status": repo_status,
            "last_scan": timestamp,
            "default_branch": git.default_branch,
            "active_branch": git.active_branch,
            "open_failures": open_failures,
            "stale_pr_count": "UNKNOWN" if not git.has_origin else health.get("stale_pr_count", "UNKNOWN"),
            "next_action": (
                "Connect direct GitHub access and rerun the refresh to replace unknown PR and CI fields with observed data."
                if not git.has_origin
                else "Review hydrated PR and CI trackers, then remediate the highest-severity blocker."
            ),
            "browser_rejection": browser_rejection,
        }
    )
    write_json(HEALTH_PATH, health)

    pr_tracking = read_json(PR_PATH)
    pr_tracking.update(
        {
            "last_scan": timestamp,
            "integration_status": github_integration,
            "unknowns": [] if git.has_origin else [
                "No Git remote is configured in the local checkout.",
                "No authenticated GitHub query path is available from this workspace.",
            ],
            "global_next_action": (
                "Query the canonical Git provider for open PRs and update per-PR blocker records."
                if git.has_origin
                else "Wire direct GitHub access, then hydrate this tracker with live PR metadata and remediation steps."
            ),
        }
    )
    write_json(PR_PATH, pr_tracking)

    ci_tracking = read_json(CI_PATH)
    ci_tracking.update(
        {
            "last_scan": timestamp,
            "workflows": [Path(path).stem for path in validation.workflow_files],
            "failure_patterns": (
                ci_tracking.get("failure_patterns", []) if git.has_origin else ["UNKNOWN, remote workflow history not available from local-only refresh"]
            ),
            "remediation_notes": [
                "Run local parity checks for control-center changes before claiming operational readiness.",
                "Remote CI state must come from a direct integration, not from assumptions.",
            ],
            "next_action": (
                "Hydrate recent failure history from the canonical CI provider and attach root-cause notes per broken workflow."
                if git.has_origin
                else "Connect the canonical CI provider so workflow failures can be tracked with real telemetry."
            ),
        }
    )
    write_json(CI_PATH, ci_tracking)

    report_lines = [
        "# CTO Daily Status",
        "",
        f"Overall ecosystem health: {repo_status.title()}",
        "",
        "## Critical repos",
        "",
        "- repo name: openclaw",
        f"  - health status: {repo_status.title()}",
        "  - main blocker:",
        *wrap_line("    ", open_failures[0]["summary"] if open_failures else "No blockers were found in local inspection."),
        "  - exact next step:",
        *wrap_line("    ", health["next_action"]),
        "",
        "## PR status",
        "",
        f"- merge-ready: {'UNKNOWN' if not git.has_origin else len(pr_tracking['merge_ready_prs'])}",
        f"- blocked: {'UNKNOWN' if not git.has_origin else len(pr_tracking['blocked_prs'])}",
        f"- stale: {'UNKNOWN' if not git.has_origin else len(pr_tracking['stale_prs'])}",
        f"- failing checks: {'UNKNOWN' if not git.has_origin else len(pr_tracking['failing_prs'])}",
        "",
        "## CI status",
        "",
        f"- failing workflows: {'UNKNOWN' if not git.has_origin else len(ci_tracking['recent_failures'])}",
        "- workflow inventory:",
        *wrap_line("  ", ", ".join(ci_tracking["workflows"])),
        "",
        "## Actions completed",
        "",
        "- validated the CTO control-center structure and registry",
        "- refreshed local health, PR, and CI tracking state",
        "- regenerated daily and weekly reports from direct repository inspection",
        "- preserved unknown remote state as UNKNOWN or MISSING INTEGRATION instead of guessing",
        "",
        "## Top risks",
        "",
    ]
    if open_failures:
        for failure in open_failures:
            report_lines.extend(wrap_line("- ", failure["summary"]))
    else:
        report_lines.append("- No locally-detected control-center blockers.")
    report_lines.extend(
        [
            "",
            "## Next highest-leverage actions",
            "",
            "1. Connect direct GitHub access and rerun the refresh.",
            "   Replace unknown PR and CI fields with observed data.",
            "   This is the single most important blocker in this workspace.",
            *wrap_line("2. ", "Add direct MCP task integration if task audit trails are required in this workspace."),
            *wrap_line("3. ", "Expand the repository registry when additional repositories become directly accessible."),
        ]
    )
    write_text(REPORTS_DIR / f"daily-{today}.md", "\n".join(report_lines))

    weekly_lines = [
        "# CTO Systems Report",
        "",
        f"## Week ending {today}",
        "",
        "### Status summary",
        "",
        f"- Ecosystem health is {repo_status.title()}.",
        f"- GitHub integration status is {github_integration}.",
        "- Repository coverage is limited to repositories directly accessible from this workspace.",
        "",
        "### What changed",
        "",
        "- Validated the control-center file structure and registry requirements.",
        "- Refreshed local health, PR, and CI tracker state from direct inspection.",
        "- Regenerated reproducible daily and weekly CTO reports.",
        "- Preserved unknown upstream data as explicit unknowns.",
        "",
        "### Current blockers",
        "",
    ]
    if open_failures:
        for failure in open_failures:
            weekly_lines.extend(wrap_line(f"- {failure['id']}: ", failure["summary"]))
    else:
        weekly_lines.append("- No locally-detected control-center blockers.")
    weekly_lines.extend(
        [
            "",
            "### Risk ranking",
            "",
            "1. Unknown upstream CI and PR health when the canonical Git remote is unavailable.",
            "2. Missing task audit trail when MCP task integration is unavailable.",
            "3. Incomplete cross-repository visibility outside this workspace.",
            "",
            "### Next week",
            "",
            "1. Connect direct GitHub telemetry.",
            "2. Hydrate live PR and CI state.",
            "3. Add automation scripts to refresh trackers from direct integrations.",
        ]
    )
    write_text(REPORTS_DIR / f"weekly-{today}.md", "\n".join(weekly_lines))

    run_log = {
        "timestamp": timestamp,
        "execution_path": standards.get("execution_priority", []),
        "browser_rejection": browser_rejection,
        "files_used": [
            str(CONFIG.relative_to(ROOT)),
            str(REGISTRY.relative_to(ROOT)),
            str(BOOTSTRAP_STATE_PATH.relative_to(ROOT)),
            str(HEALTH_PATH.relative_to(ROOT)),
            str(PR_PATH.relative_to(ROOT)),
            str(CI_PATH.relative_to(ROOT)),
        ],
        "actions_taken": [
            "validated required CTO paths",
            "validated registry field coverage",
            "refreshed health, PR, and CI tracker JSON files",
            "regenerated daily and weekly markdown reports",
        ],
        "result": {
            "repo_status": repo_status,
            "github_integration": github_integration,
            "active_branch": git.active_branch,
            "default_branch": git.default_branch,
            "workflow_count": len(validation.workflow_files),
        },
        "blockers": [failure["summary"] for failure in open_failures],
        "retry_or_escalation_state": (
            "Retry after configuring a direct GitHub remote or authenticated provider integration."
            if not git.has_origin
            else "No escalation required from local validation."
        ),
    }
    write_json(RUN_LOG_PATH, run_log)
    return open_failures


def main() -> int:
    import sys

    failures = refresh()
    if "--check" not in sys.argv:
        return 0
    blocking_ids = {"control_center.structure_missing", "control_center.registry_incomplete"}
    blocking = [failure for failure in failures if failure["id"] in blocking_ids]
    if blocking:
        for failure in blocking:
            print(f"BLOCKING: {failure['id']} :: {failure['summary']}")
        return 1
    print("CTO control center structure validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
