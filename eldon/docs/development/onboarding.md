# OpenClaw Python onboarding

This flow sets up a local Python development environment for `eldon/src/openclaw`.

## Prerequisites

1. Python 3.11 or newer.
2. `uv` installed.
3. Run all commands from the `eldon/` directory.

## Local setup flow

1. Create a repo-local virtual environment:

```bash
uv venv .venv
```

2. Activate the virtual environment:

```bash
source .venv/bin/activate
```

3. Install runtime and dev dependencies:

```bash
uv pip install -e config[dev]
uv pip install ruff mypy
```

4. Run preflight to verify the Python package path:

```bash
PYTHONPATH=src uv run python scripts/preflight.py
```

5. Run the complete local validation chain:

```bash
uv run python scripts/local_validate.py
```

## Expected output

A successful run ends with:

```text
local_validate: all checks passed
```

## Troubleshooting

- If import checks fail, confirm `PYTHONPATH=src` is set for commands.
- If `mypy` or `ruff` are missing, reinstall them with `uv pip install ruff mypy`.
- If pytest discovers no tests, verify you are running from `eldon/`.
