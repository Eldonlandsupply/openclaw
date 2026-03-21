# Repo Agent Tool Policy

## Allowed
- read, write, edit, apply_patch — core tools
- exec — for building, testing, linting; non-destructive operations preferred
- web_fetch — for docs and dependency info

## Restricted
- exec with git push / git commit — requires orchestrator sign-off
- Modifying .env, secrets, deployment manifests — escalate first
- sessions_spawn — only to delegate scoped subtasks

## Guidance
Prefer edit over full write for existing files. Always diff before committing.
