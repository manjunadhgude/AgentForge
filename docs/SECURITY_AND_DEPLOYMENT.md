# AgentForge Security and Deployment Notes

## Current scope

AgentForge is a tested local reliability prototype. The current demo and benchmark use simulated operations. Do not expose the API to the public internet or connect it to real money movement, refunds, account changes, or other high-impact operations until the controls below have been reviewed and tested.

## Secrets and configuration

- Keep database passwords, API tokens, and signing keys in environment variables or a dedicated secrets manager.
- Never commit `.env` files, credentials, production connection strings, or real customer data.
- Rotate any credential that may have been committed or shared.
- Use least-privilege database accounts and separate development, test, and production credentials.
- Do not print secrets in logs or error messages.

## API hardening before deployment

- Require authentication for every non-public endpoint.
- Enforce authorization per operation and per resource; authentication alone is insufficient.
- Validate request bodies and enforce size, rate, and timeout limits.
- Return safe error messages without stack traces, SQL, secrets, or internal paths.
- Configure explicit CORS origins if browser clients are used.
- Disable debug mode and interactive API documentation in production unless access-controlled.
- Add structured access logs, request IDs, and security-relevant audit events.
- Run behind TLS and a maintained reverse proxy or managed ingress.
- Pin and review dependencies; apply security updates and run dependency scanning in CI.

## Side-effect safety

- Use downstream idempotency keys when the external provider supports them.
- Treat timeouts after a side-effect request as uncertain, not as proof of failure.
- Reconcile uncertain actions against the downstream system before retrying.
- Require explicit human approval for high-impact or ambiguous actions.
- Keep the action ledger and side-effecting provider consistent through a documented reconciliation process.
- Test duplicate requests, stale workers, lease expiry, and worker restarts.

## Database operations

- Do not delete, recreate, or reset the existing development PostgreSQL database or Docker volume as a test shortcut.
- Use a dedicated disposable database for migration and destructive integration tests.
- Take and verify a backup before schema migrations or any destructive operation.
- Use TLS and restricted network access for remote databases.
- Verify database permissions and connection-pool behavior under expected load.

## LLM proposal boundary

The optional `/llm/propose` route requires the API bearer token and returns a proposal only. It does not execute tools. The tool registry is authoritative for allowlisting and schema validation, and side-effecting tools still require a matching explicit approval through the normal execution route. Keep provider credentials in environment variables; do not include them in screenshots, logs, source files, or issue reports.

## Release gate

A successful local test suite is necessary but not sufficient for production release. Require passing integration tests, crash/restart recovery tests, authentication and authorization tests, dependency/security checks, operational alerts, backup/restore verification, and a reviewed deployment rollback plan.
