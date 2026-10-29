# AgentForge Final Hardening Checklist

This checklist distinguishes current local evidence from work that still needs dedicated validation.

## Historical evidence from an earlier run (not the latest verification)

- [x] Python compilation passed.
- [x] Full regression suite: 97 tests passed.
- [x] Local demo completed and replayed the saved result without invoking the simulated tool twice.
- [x] Demo reported no external service calls and no irreversible operations.
- [x] Local simulated retry benchmark completed.
- [x] Architecture, operations, project status, and release-readiness documentation exists.

## Batch 7 checks

- [ ] Re-run full test suite on the current checkout.
- [ ] Check installed dependency consistency with `pip check`.
- [ ] Scan tracked project source/documentation for likely hard-coded credentials.
- [ ] Run `git diff --check`.
- [ ] If `AGENTFORGE_DB_PASSWORD` is already configured in this PowerShell session, run a read-only PostgreSQL connectivity check (`SELECT 1` and current database/user only).
- [ ] Review the generated hardening audit and every secret-scan finding manually.

## Required before production claims

- [ ] Add and run PostgreSQL integration tests against an isolated test database.
- [ ] Add a real process termination/restart test for in-flight and uncertain actions.
- [ ] Verify reconciliation with a fake downstream provider and downstream idempotency keys.
- [ ] Test API authentication, authorization, rate limits, and unsafe-input handling.
- [ ] Run dependency vulnerability scanning and a security review.
- [ ] Verify backups can be restored and document rollback procedures.
- [ ] Review and deliberately stage files; do not blindly run `git add .`.
- [ ] Commit the reviewed release and tag it only after release gates pass.

A checkbox must not be marked complete solely because documentation describes the control.
