# Contributing to AgentForge

Thanks for helping improve AgentForge.

## Scope and expectations

AgentForge is a reliability-focused engineering prototype for tool-using workflows. Contributions should preserve conservative handling of uncertain outcomes and clearly distinguish simulated results from real provider or production evidence.

## Development setup

Use Python 3.12 as documented in the README. From the repository root, create/activate a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

On Windows PowerShell, activate `.venv\Scripts\Activate.ps1` and use the same Python commands.

## Before submitting

1. Add or update tests for behavior changes, especially retries, lease ownership, uncertain outcomes, approvals, and replay.
2. Run `python -m pytest -q`.
3. Run `python -m pip check` and `python -m pip_audit` where available.
4. Run the demo and relevant benchmark if your change affects them.
5. Run `git diff --check`.
6. Review `git diff` and ensure no credentials, `.env`, database dumps, caches, or generated local artifacts are included.

## Pull requests

Describe the problem, the design choice, tests run, limitations, and any compatibility or security implications. Do not claim exactly-once external execution unless a destination-side idempotency/reconciliation design and evidence support that claim.
