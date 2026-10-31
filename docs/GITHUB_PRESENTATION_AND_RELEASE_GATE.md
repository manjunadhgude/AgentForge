# GitHub Presentation and Release Gate

## Intended project positioning

AgentForge is a **reliability-focused engineering prototype / reliability lab**. The repository should demonstrate careful recovery semantics, tests, reproducible local experiments, and honest limitations. Passing local checks does not make it production-ready.

## Public-repository acceptance criteria

- [ ] README states the purpose, capabilities, setup, test commands, benchmark commands, and limitations.
- [ ] Architecture and operations documentation match the implementation.
- [ ] CI runs tests on pull requests and pushes.
- [ ] Dependency audit runs in CI and findings are reviewed.
- [ ] Security policy, contribution guidance, and issue/PR templates exist.
- [ ] Tests cover completed-result replay, mismatched action keys, lease ownership, process recovery, approvals, API authentication, and uncertain outcomes.
- [ ] The demo is deterministic/safe and labels simulated operations clearly.
- [ ] Benchmark reports state their scope and do not imply competitor or production performance.
- [ ] `.env`, virtual environments, database files/dumps, credentials, and transient logs are excluded from Git.
- [ ] Generated reports and the complete Git diff are reviewed before release.
- [ ] The published default branch and GitHub Actions results are inspected after pushing.

## Technical limitations to keep visible

- A ledger alone cannot guarantee exactly-once execution of arbitrary remote side effects.
- A timeout may mean the remote operation succeeded even when the caller did not receive confirmation.
- Real side-effecting integrations require destination-side idempotency keys or equivalent deduplication, durable reconciliation, and an explicit uncertain-outcome path.
- Leases coordinate workers but do not alone provide a general distributed fencing guarantee.
- The default demo and retry benchmark are simulated local experiments, not production load tests or fair comparisons with Temporal, Inngest, LangGraph, or other products.
- The development API has not been security-certified. Public deployment needs reviewed TLS, authorization, rate limits, secret management, monitoring, alerting, backup/restore procedures, and rollback.

## Release rule

Do not mark an item complete merely because it is described in documentation. Mark it complete only when code, tests, and recorded evidence support it. Do not commit or push automatically from a hardening script.
