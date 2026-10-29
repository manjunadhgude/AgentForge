# AgentForge Operations Runbook

## Standard local verification

Run from the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m py_compile action_ledger.py action_runtime.py resilience.py observability.py api.py demo_agentforge.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe demo_agentforge.py
.\.venv\Scripts\python.exe benchmarks\run_reliability_benchmark.py --iterations 50
.\.venv\Scripts\python.exe -m pip check
```

Pytest ignores `backups/`, `.venv/`, `.git/`, and cache directories. PostgreSQL integration tests skip when `AGENTFORGE_DB_PASSWORD` is not set. To explicitly run them, confirm the target database is a development/test database, set the variable in the current shell, then run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m postgres
```

These integration tests write test rows/checkpoints. They are not read-only diagnostics.

## Expected demo properties

- `external_services_called` is `false`.
- `irreversible_actions_performed` is `false`.
- The first action execution completes and is not replayed.
- The second execution returns the saved result and is marked replayed.
- The simulated tool invocation count remains one.

## Benchmark expectations

- `success`: all iterations succeed in one attempt.
- `transient_recovery`: all iterations recover on the configured second attempt.
- `exhausted_retries`: all iterations fail after the configured retry limit.
- Treat latency values as local simulated microbenchmark observations only.

## Database safety

- Do not delete or recreate the existing PostgreSQL container or volume as a test shortcut.
- Before any schema migration or destructive database operation, take a verified backup and inspect the target database and command.
- Prefer in-memory or temporary SQLite for isolated tests and demos.
- Never paste database passwords, API keys, or other secrets into chat or commit them to Git.
- Set `AGENTFORGE_DB_PASSWORD` only in the local shell/session that needs it.

## Git hygiene

Inspect before staging:

```powershell
git status --short
git diff --check
git diff --stat
```

Do not use blanket `git add .` without inspecting the status first. Do not commit secrets, local database files, virtual environments, backups, or transient output.
