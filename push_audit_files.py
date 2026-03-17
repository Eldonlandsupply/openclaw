#!/usr/bin/env python3
"""
OpenClaw Audit Fix Pusher
Pushes 16 audit fix files to Eldonlandsupply/EldonOpenClaw @ feature/imessage-notifier
Usage: python push_audit_files.py YOUR_GITHUB_TOKEN
"""

import base64
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = "Eldonlandsupply/EldonOpenClaw"
BRANCH = "feature/imessage-notifier"
TOKEN = sys.argv[1] if len(sys.argv) > 1 else input("GitHub token: ").strip()

FILES = {
    "agents/base_agent.py": (
        "fix: enforce tool permission boundaries on base agent",
        '''class BaseAgent:
    def __init__(self, name, role, permissions=None):
        self.name = name
        self.role = role
        self.permissions = permissions or []
        self.memory = []
        self.status = "idle"

    def can_use_tool(self, tool_name):
        return tool_name in self.permissions

    def invoke_tool(self, tool_name, *args, **kwargs):
        if not self.can_use_tool(tool_name):
            raise PermissionError(f"Agent '{self.name}' not permitted to use '{tool_name}'")
        return self._execute_tool(tool_name, *args, **kwargs)

    def _execute_tool(self, tool_name, *args, **kwargs):
        raise NotImplementedError

    def log(self, event):
        self.memory.append({"event": event, "agent": self.name})
''',
    ),
    "agents/orchestrator.py": (
        "fix: add human-in-the-loop checkpoint before risky delegations",
        '''class Orchestrator:
    def __init__(self, agents, approval_required_for=None):
        self.agents = {a.name: a for a in agents}
        self.approval_required_for = approval_required_for or []
        self.pending_approvals = []

    def delegate(self, task, agent_name, require_approval=False):
        if require_approval or task.get("risk_level") in self.approval_required_for:
            self.pending_approvals.append({"task": task, "agent": agent_name})
            return {"status": "pending_approval"}
        return self._run(task, agent_name)

    def approve(self, task_id):
        task = self.pending_approvals.pop(task_id)
        return self._run(task["task"], task["agent"])

    def _run(self, task, agent_name):
        agent = self.agents.get(agent_name)
        if not agent:
            raise ValueError(f"No agent named '{agent_name}'")
        return agent.handle(task)
''',
    ),
    "memory/memory_manager.py": (
        "fix: separate durable vs transient memory with TTL enforcement",
        '''import time

class MemoryManager:
    def __init__(self):
        self.durable = {}
        self.transient = {}

    def store_durable(self, key, value):
        self.durable[key] = {"value": value, "created_at": time.time()}

    def store_transient(self, key, value, ttl_seconds=3600):
        self.transient[key] = {"value": value, "expires_at": time.time() + ttl_seconds}

    def get(self, key):
        if key in self.durable:
            return self.durable[key]["value"]
        entry = self.transient.get(key)
        if entry and entry["expires_at"] > time.time():
            return entry["value"]
        return None

    def purge_expired(self):
        now = time.time()
        self.transient = {k: v for k, v in self.transient.items() if v["expires_at"] > now}
''',
    ),
    "hooks/event_hooks.py": (
        "fix: add idempotency keys to all hook invocations",
        '''import hashlib
import json
import time

class EventHookRunner:
    def __init__(self):
        self.seen_keys = set()
        self.log = []

    def _idempotency_key(self, hook_name, payload):
        raw = json.dumps({"hook": hook_name, "payload": payload}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def run(self, hook_name, payload, handler_fn):
        key = self._idempotency_key(hook_name, payload)
        if key in self.seen_keys:
            return {"status": "skipped", "reason": "duplicate"}
        self.seen_keys.add(key)
        result = handler_fn(payload)
        self.log.append({"hook": hook_name, "key": key, "at": time.time()})
        return result
''',
    ),
    "dashboard/api_routes.py": (
        "fix: add auth middleware to all dashboard API routes",
        '''from functools import wraps

VALID_TOKENS = set()


def require_auth(fn):
    @wraps(fn)
    def wrapper(request, *args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token not in VALID_TOKENS:
            return {"error": "Unauthorized"}, 401
        return fn(request, *args, **kwargs)

    return wrapper


@require_auth
def get_agents(request):
    return {"agents": []}, 200


@require_auth
def get_jobs(request):
    return {"jobs": []}, 200


@require_auth
def approve_task(request, task_id):
    return {"approved": task_id}, 200
''',
    ),
    "jobs/job_runner.py": (
        "fix: add retry with exponential backoff and dead-letter queue",
        '''import time

class JobRunner:
    def __init__(self, max_retries=3, base_delay=2):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.dead_letter = []

    def run(self, job_fn, payload, job_id=None):
        attempt = 0
        while attempt <= self.max_retries:
            try:
                result = job_fn(payload)
                return {"status": "success", "result": result, "attempts": attempt + 1}
            except Exception as e:
                attempt += 1
                if attempt > self.max_retries:
                    self.dead_letter.append({"job_id": job_id, "error": str(e)})
                    return {"status": "failed", "error": str(e)}
                time.sleep(self.base_delay ** attempt)
''',
    ),
    "security/secrets.py": (
        "fix: centralize secrets access — no inline env var reads",
        '''import os

_cache = {}


def get_secret(key):
    if key in _cache:
        return _cache[key]
    value = os.environ.get(key)
    if not value:
        raise EnvironmentError(f"Secret '{key}' not set in environment")
    _cache[key] = value
    return value


def require_secrets(*keys):
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required secrets: {missing}")
''',
    ),
    "audit/audit_trail.py": (
        "fix: make audit trail append-only with tamper detection",
        '''import hashlib
import json
import time

class AuditTrail:
    def __init__(self):
        self.entries = []

    def _hash(self, entry, prev_hash=""):
        raw = json.dumps(entry, sort_keys=True) + prev_hash
        return hashlib.sha256(raw.encode()).hexdigest()

    def append(self, actor, action, payload):
        prev_hash = self.entries[-1]["hash"] if self.entries else ""
        entry = {"at": time.time(), "actor": actor, "action": action, "payload": payload}
        entry["hash"] = self._hash(entry, prev_hash)
        self.entries.append(entry)

    def verify(self):
        prev_hash = ""
        for e in self.entries:
            expected = self._hash({k: v for k, v in e.items() if k != "hash"}, prev_hash)
            if e["hash"] != expected:
                return False
            prev_hash = e["hash"]
        return True
''',
    ),
    "routing/task_router.py": (
        "fix: prevent routing loops and orphaned tasks",
        '''class TaskRouter:
    def __init__(self, routes):
        self.routes = routes
        self.in_flight = set()

    def route(self, task):
        task_id = task.get("id")
        if task_id in self.in_flight:
            raise RuntimeError(f"Routing loop detected for task {task_id}")
        self.in_flight.add(task_id)
        try:
            handler = self.routes.get(task.get("type"))
            if not handler:
                raise ValueError(f"No route for task type '{task.get('type')}'")
            return handler(task)
        finally:
            self.in_flight.discard(task_id)
''',
    ),
    "agents/agent_registry.py": (
        "fix: enforce unique agent IDs and prevent duplicate registration",
        '''class AgentRegistry:
    def __init__(self):
        self._agents = {}

    def register(self, agent):
        if agent.name in self._agents:
            raise ValueError(f"Agent '{agent.name}' already registered")
        self._agents[agent.name] = agent

    def get(self, name):
        agent = self._agents.get(name)
        if not agent:
            raise KeyError(f"No agent '{name}' in registry")
        return agent

    def all(self):
        return list(self._agents.values())

    def deregister(self, name):
        if name not in self._agents:
            raise KeyError(f"Cannot deregister unknown agent '{name}'")
        del self._agents[name]
''',
    ),
    "monitoring/health_check.py": (
        "fix: structured health check endpoint for all subsystems",
        '''import time

class HealthChecker:
    def __init__(self):
        self.checks = {}

    def register(self, name, check_fn):
        self.checks[name] = check_fn

    def run_all(self):
        results = {}
        overall = "healthy"
        for name, fn in self.checks.items():
            try:
                ok = fn()
                results[name] = {"status": "ok" if ok else "degraded"}
                if not ok:
                    overall = "degraded"
            except Exception as e:
                results[name] = {"status": "error", "detail": str(e)}
                overall = "error"
        return {"overall": overall, "at": time.time(), "checks": results}
''',
    ),
    "config/agent_schema.py": (
        "fix: add schema validation for agent config at load time",
        '''REQUIRED_FIELDS = ["name", "role", "permissions", "memory_profile", "tools"]


def validate_agent_config(config):
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in config:
            errors.append(f"Missing required field: '{field}'")
    if not isinstance(config.get("permissions", []), list):
        errors.append("'permissions' must be a list")
    if not isinstance(config.get("tools", []), list):
        errors.append("'tools' must be a list")
    if errors:
        raise ValueError(f"Invalid agent config: {errors}")
    return True
''',
    ),
    "collaboration/silo_manager.py": (
        "fix: enforce silo boundaries — prevent cross-silo agent access",
        '''class SiloManager:
    def __init__(self):
        self.silos = {}

    def create_silo(self, name, agent_names):
        self.silos[name] = set(agent_names)

    def can_collaborate(self, agent_a, agent_b):
        for members in self.silos.values():
            if agent_a in members and agent_b in members:
                return True
        return False

    def assert_can_collaborate(self, agent_a, agent_b):
        if not self.can_collaborate(agent_a, agent_b):
            raise PermissionError(
                f"Agents '{agent_a}' and '{agent_b}' are in different silos"
            )
''',
    ),
    "cron/cron_manager.py": (
        "fix: prevent duplicate cron job registration and add enable/disable",
        '''import time

class CronManager:
    def __init__(self):
        self.jobs = {}

    def register(self, name, fn, interval_seconds, enabled=True):
        if name in self.jobs:
            raise ValueError(f"Cron job '{name}' already registered")
        self.jobs[name] = {"fn": fn, "interval": interval_seconds, "enabled": enabled, "last_run": None}

    def toggle(self, name, enabled):
        if name not in self.jobs:
            raise KeyError(f"No cron job '{name}'")
        self.jobs[name]["enabled"] = enabled

    def tick(self):
        now = time.time()
        for name, job in self.jobs.items():
            if not job["enabled"]:
                continue
            if job["last_run"] is None or now - job["last_run"] >= job["interval"]:
                job["fn"]()
                job["last_run"] = now
''',
    ),
    "observability/logger.py": (
        "fix: structured JSON logging with consistent schema across all agents",
        '''import json
import sys
import time

class StructuredLogger:
    def __init__(self, service_name):
        self.service = service_name

    def _emit(self, level, message, **context):
        entry = {"at": time.time(), "level": level, "service": self.service, "message": message, **context}
        print(json.dumps(entry), file=sys.stderr)

    def info(self, message, **ctx):
        self._emit("INFO", message, **ctx)

    def warn(self, message, **ctx):
        self._emit("WARN", message, **ctx)

    def error(self, message, **ctx):
        self._emit("ERROR", message, **ctx)

    def debug(self, message, **ctx):
        self._emit("DEBUG", message, **ctx)
''',
    ),
    "notifiers/imessage_notifier.py": (
        "fix: add retry, error handling, and structured logging to iMessage notifier",
        '''import subprocess
import time

from observability.logger import StructuredLogger

logger = StructuredLogger("imessage-notifier")


def send_imessage(recipient, message, retries=3, delay=2):
    script = f"""
tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    set targetBuddy to buddy "{recipient}" of targetService
    send "{message}" to targetBuddy
end tell
"""
    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("iMessage sent", recipient=recipient, attempt=attempt)
                return True
            logger.warn("iMessage failed", stderr=result.stderr, attempt=attempt)
        except Exception as e:
            logger.error("iMessage error", error=str(e), attempt=attempt)
        if attempt < retries:
            time.sleep(delay ** attempt)
    return False
''',
    ),
}


def api(method, path, body=None):
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req) as response:
            return json.loads(response.read()), response.status
    except HTTPError as e:
        return json.loads(e.read()), e.code


def get_sha(path):
    data, status = api("GET", f"/repos/{REPO}/contents/{path}?ref={BRANCH}")
    if status == 200:
        return data.get("sha")
    return None


def push_file(path, commit_msg, content):
    sha = get_sha(path)
    body = {
        "message": commit_msg,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    _, status = api("PUT", f"/repos/{REPO}/contents/{path}", body)
    return status in (200, 201)


def main():
    print("\nOpenClaw Audit Pusher")
    print(f"Repo:   {REPO}")
    print(f"Branch: {BRANCH}")
    print(f"Files:  {len(FILES)}\n")

    ok_count = 0
    fail_count = 0

    for path, (msg, content) in FILES.items():
        result = push_file(path, msg, content)
        status_icon = "✓" if result else "✗"
        print(f"  {status_icon}  {path}")
        if result:
            ok_count += 1
        else:
            fail_count += 1

    print(f"\n{'─' * 50}")
    print(f"Done: {ok_count} pushed, {fail_count} failed")
    if fail_count == 0:
        print("All audit fixes live on feature/imessage-notifier ✓")
    else:
        print("Check token scope (needs repo) and repo name spelling.")


if __name__ == "__main__":
    main()
