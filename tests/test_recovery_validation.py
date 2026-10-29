from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, update

from action_ledger import (
    actions,
    claim_action,
    complete_action,
    get_action,
    get_recovery_decision,
    initialize_ledger,
    mark_action_uncertain,
    reclaim_expired_lease,
)


@pytest.fixture
def engine():
    value = create_engine("sqlite+pysqlite:///:memory:")
    initialize_ledger(value)
    yield value
    value.dispose()


def test_missing_action_recovery_decision_is_not_found(engine):
    assert get_recovery_decision(get_action(engine, "missing")) == "not_found"


def test_new_claim_is_in_progress_and_requires_inspection(engine):
    claim = claim_action(engine, "recovery-001", "demo", {"n": 1}, lease_owner="worker-a")
    assert claim["claimed"] is True
    assert get_recovery_decision(claim) == "inspect_before_retry"


def test_completed_action_recovery_uses_saved_result(engine):
    claim_action(engine, "recovery-002", "demo", {"n": 2}, lease_owner="worker-a")
    complete_action(engine, "recovery-002", {"answer": 42}, lease_owner="worker-a")
    saved = get_action(engine, "recovery-002")
    assert saved["status"] == "completed"
    assert get_recovery_decision(saved) == "use_saved_result"
    assert saved["result_payload"] == {"answer": 42}


def test_uncertain_action_requires_reconciliation(engine):
    claim_action(engine, "recovery-003", "demo", {"n": 3}, lease_owner="worker-a")
    mark_action_uncertain(engine, "recovery-003", lease_owner="worker-a")
    saved = get_action(engine, "recovery-003")
    assert saved["status"] == "uncertain"
    assert get_recovery_decision(saved) == "reconcile_or_escalate"


def _expire_lease(engine, action_key):
    expired = datetime.now(timezone.utc) - timedelta(seconds=30)
    with engine.begin() as connection:
        connection.execute(
            update(actions)
            .where(actions.c.action_key == action_key)
            .values(lease_expires_at=expired)
        )


def test_expired_in_progress_lease_can_be_reclaimed_once(engine):
    claim_action(engine, "recovery-004", "demo", {"n": 4}, lease_owner="worker-a")
    _expire_lease(engine, "recovery-004")
    assert reclaim_expired_lease(engine, "recovery-004", "worker-b", lease_seconds=60) is True
    assert reclaim_expired_lease(engine, "recovery-004", "worker-c", lease_seconds=60) is False
    with engine.connect() as connection:
        row = connection.execute(
            actions.select().where(actions.c.action_key == "recovery-004")
        ).mappings().one()
    assert row["lease_owner"] == "worker-b"
    assert row["status"] == "in_progress"


def test_stale_worker_cannot_complete_after_lease_reclaimed(engine):
    claim_action(engine, "recovery-005", "demo", {"n": 5}, lease_owner="worker-a")
    _expire_lease(engine, "recovery-005")
    assert reclaim_expired_lease(engine, "recovery-005", "worker-b", lease_seconds=60)
    with pytest.raises(ValueError, match="lease expired|does not own"):
        complete_action(engine, "recovery-005", {"unsafe": True}, lease_owner="worker-a")
    complete_action(engine, "recovery-005", {"safe": True}, lease_owner="worker-b")
    assert get_action(engine, "recovery-005")["result_payload"] == {"safe": True}


def test_stale_worker_cannot_mark_action_uncertain_after_reclaim(engine):
    claim_action(engine, "recovery-006", "demo", {"n": 6}, lease_owner="worker-a")
    _expire_lease(engine, "recovery-006")
    assert reclaim_expired_lease(engine, "recovery-006", "worker-b", lease_seconds=60)
    with pytest.raises(ValueError, match="lease expired|does not own"):
        mark_action_uncertain(engine, "recovery-006", lease_owner="worker-a")
    assert get_action(engine, "recovery-006")["status"] == "in_progress"


def test_expired_lease_cannot_be_reclaimed_when_action_is_completed(engine):
    claim_action(engine, "recovery-007", "demo", {"n": 7}, lease_owner="worker-a")
    complete_action(engine, "recovery-007", {"done": True}, lease_owner="worker-a")
    assert reclaim_expired_lease(engine, "recovery-007", "worker-b") is False


def test_action_key_cannot_be_reused_for_different_payload(engine):
    claim_action(engine, "recovery-008", "demo", {"n": 8}, lease_owner="worker-a")
    with pytest.raises(ValueError, match="different request"):
        claim_action(engine, "recovery-008", "demo", {"n": 80}, lease_owner="worker-b")


def test_expired_lease_cannot_be_reclaimed_by_same_owner(engine):
    action_key = "recovery-009"
    claim_action(engine, action_key, "demo", {"n": 9}, lease_owner="worker-a")
    _expire_lease(engine, action_key)

    # Reusing the same owner identity defeats stale-worker protection.
    assert reclaim_expired_lease(
        engine, action_key, "worker-a", lease_seconds=60
    ) is False
    row = get_action(engine, action_key)
    assert row["status"] == "in_progress"
