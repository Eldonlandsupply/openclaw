# PyCharm setup for OpenClaw Python

Use this setup for consistent local behavior across contributors.

## Required project settings

1. Interpreter: use repo-local `.venv` at `eldon/.venv`.
2. Mark `src/` as **Sources Root**.
3. Mark `tests/` as **Test Sources Root**.
4. Test runner: set to **pytest**.
5. Share run configurations only, save them under `.idea/runConfigurations`.

## Recommended shared run configurations

Create and commit only shared configurations:

1. `preflight`:
   - Script: `scripts/preflight.py`
   - Environment: `PYTHONPATH=src`
2. `local_validate`:
   - Script: `scripts/local_validate.py`
   - Environment: `PYTHONPATH=src`
3. `pytest`:
   - Target: `tests`
   - Additional options: `-q`
   - Environment: `PYTHONPATH=src`

## Verification

After setting PyCharm, run `local_validate` from the IDE and confirm it completes without errors.
