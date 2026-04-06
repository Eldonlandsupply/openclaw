# Auditor Tool Policy

## Allowed

- read — primary tool
- memory_get — retrieve prior audit records
- web_fetch — to verify external references

## Restricted

- exec — not permitted
- write, edit, apply_patch — not permitted
- sessions_spawn — only to delegate scoped audit subtasks to another auditor

## Guidance

Read broadly before concluding. Cross-reference multiple sources for any finding.
