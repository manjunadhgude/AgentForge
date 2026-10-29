import pytest
from sqlalchemy import create_engine, select

from action_ledger import (
    actions,
    claim_action,
    complete_action,
    get_action,
    initialize_ledger,
    mark_action_uncertain,
    get_recovery_decision,
)

@pytest.fixture
def engine():
    test_engine = create_engine("sqlite:///:memory:")
    initialize_ledger(test_engine)
    yield test_engine
    test_engine.dispose()


def test_duplicate_request_is_not_claimed_twice(engine):
    request = {"incident_id": "INC-001"}

    first = claim_action(
        engine, "action-001", "inspect_service", request
    )
    second = claim_action(
        engine, "action-001", "inspect_service", request
    )

    assert first["claimed"] is True
    assert second["claimed"] is False
    assert second["status"] == "in_progress"


def test_completed_action_stores_result(engine):
    claim_action(
        engine,
        "action-002",
        "inspect_service",
        {"incident_id": "INC-002"},
    )

    complete_action(
        engine,
        "action-002",
        {"health_status": "healthy"},
        lease_owner="worker-1",
    )

    with engine.connect() as connection:
        saved = connection.execute(
            select(actions).where(
                actions.c.action_key == "action-002"
            )
        ).mappings().one()

    assert saved["status"] == "completed"
    assert saved["result_payload"] == {
        "health_status": "healthy"
    }


def test_key_cannot_be_reused_for_different_request(engine):
    claim_action(
        engine,
        "action-003",
        "inspect_service",
        {"incident_id": "INC-001"},
    )

    with pytest.raises(ValueError, match="different request"):
        claim_action(
            engine,
            "action-003",
            "inspect_service",
            {"incident_id": "INC-999"},
        )

def test_in_progress_action_can_be_marked_uncertain(engine):
    claim_action(
        engine,
        "action-uncertain-001",
        "inspect_service",
        {"incident_id": "INC-001"},
    )

    mark_action_uncertain(engine, "action-uncertain-001", lease_owner="worker-1")

    with engine.connect() as connection:
        saved = connection.execute(
            select(actions).where(
                actions.c.action_key == "action-uncertain-001"
            )
        ).mappings().one()

    assert saved["status"] == "uncertain"
    assert saved["result_payload"] is None


def test_completed_action_cannot_be_marked_uncertain(engine):
    claim_action(
        engine,
        "action-uncertain-002",
        "inspect_service",
        {"incident_id": "INC-002"},
    )

    complete_action(
        engine,
        "action-uncertain-002",
        {"health_status": "healthy"},
        lease_owner="worker-1",
    )

    with pytest.raises(ValueError, match="Action not found"):
        mark_action_uncertain(engine, "action-uncertain-002", lease_owner="worker-1")

def test_uncertain_action_is_not_claimed_again(engine):
    request = {"incident_id": "INC-003"}

    first = claim_action(
        engine,
        "action-uncertain-003",
        "inspect_service",
        request,
    )

    mark_action_uncertain(engine, "action-uncertain-003", lease_owner="worker-1")

    second = claim_action(
        engine,
        "action-uncertain-003",
        "inspect_service",
        request,
    )

    assert first["claimed"] is True
    assert second["claimed"] is False
    assert second["status"] == "uncertain"


def test_completed_action_is_not_claimed_again(engine):
    request = {"incident_id": "INC-004"}
    action_key = "action-completed-004"

    claim_action(
        engine,
        action_key,
        "inspect_service",
        request,
    )

    expected_result = {"health_status": "healthy"}
    complete_action(engine, action_key, expected_result, lease_owner="worker-1")

    repeated = claim_action(
        engine,
        action_key,
        "inspect_service",
        request,
    )

    assert repeated["claimed"] is False
    assert repeated["status"] == "completed"
    assert repeated["result_payload"] == expected_result
def test_get_action_returns_saved_uncertain_status(engine):
    action_key = "action-get-uncertain-001"

    claim_action(
        engine,
        action_key,
        "inspect_service",
        {"incident_id": "INC-GET-001"},
    )
    mark_action_uncertain(
    engine,
    action_key,
    lease_owner="worker-1"
)
    result = get_action(engine, action_key)

    assert result is not None
    assert result["action_key"] == action_key
    assert result["status"] == "uncertain"
    assert result["result_payload"] is None


def test_get_action_returns_none_for_missing_action(engine):
    result = get_action(engine, "action-does-not-exist")

    assert result is None

def test_recovery_decision_for_missing_action():
    assert get_recovery_decision(None) == "not_found"


def test_recovery_decision_uses_completed_result():
    action = {"status": "completed"}

    assert get_recovery_decision(action) == "use_saved_result"


def test_recovery_decision_reconciles_uncertain_action():
    action = {"status": "uncertain"}

    assert get_recovery_decision(action) == "reconcile_or_escalate"


def test_recovery_decision_inspects_in_progress_action():
    action = {"status": "in_progress"}

    assert get_recovery_decision(action) == "inspect_before_retry"


def test_recovery_decision_rejects_unknown_status():
    import pytest

    with pytest.raises(ValueError, match="Unsupported action status"):
        get_recovery_decision({"status": "unknown"})
from datetime import datetime, timedelta, timezone


def test_claim_action_saves_lease_details(engine):
    result = claim_action(
        engine,
        "action-lease-001",
        "inspect_service",
        {"incident_id": "INC-LEASE-001"},
        lease_owner="worker-alpha",
        lease_seconds=60,
    )

    assert result["claimed"] is True
    assert result["lease_owner"] == "worker-alpha"

    now = datetime.now(timezone.utc)
    expiry = result["lease_expires_at"]

    # Allow a small margin for test execution time.
    assert now < expiry <= now + timedelta(seconds=65)


def test_duplicate_claim_preserves_original_lease(engine):
    first = claim_action(
        engine,
        "action-lease-002",
        "inspect_service",
        {"incident_id": "INC-LEASE-002"},
        lease_owner="worker-alpha",
        lease_seconds=60,
    )

    second = claim_action(
        engine,
        "action-lease-002",
        "inspect_service",
        {"incident_id": "INC-LEASE-002"},
        lease_owner="worker-beta",
        lease_seconds=120,
    )

    assert second["claimed"] is False
    assert second["lease_owner"] == first["lease_owner"]
    assert (
    second["lease_expires_at"].replace(tzinfo=timezone.utc)
    == first["lease_expires_at"]
)

def test_claim_action_rejects_empty_lease_owner(engine):
    with pytest.raises(ValueError, match="lease_owner cannot be empty"):
        claim_action(
            engine,
            "action-lease-003",
            "inspect_service",
            {"incident_id": "INC-LEASE-003"},
            lease_owner=" ",
        )


def test_claim_action_rejects_non_positive_lease(engine):
    with pytest.raises(ValueError, match="lease_seconds must be positive"):
        claim_action(
            engine,
            "action-lease-004",
            "inspect_service",
            {"incident_id": "INC-LEASE-004"},
            lease_seconds=0,
        )
def test_worker_can_take_over_expired_lease(engine):
    from action_ledger import reclaim_expired_lease
    from datetime import datetime, timedelta, timezone

    action_key = "action-reclaim-001"

    claim_action(
        engine,
        action_key,
        "inspect_service",
        {"incident_id": "INC-RECLAIM-001"},
        lease_owner="worker-alpha",
        lease_seconds=1,
    )

    # Force the lease expiry into the past for a deterministic test.
    with engine.begin() as connection:
        connection.execute(
            actions.update()
            .where(actions.c.action_key == action_key)
            .values(
                lease_expires_at=(
                    datetime.now(timezone.utc) - timedelta(seconds=10)
                )
            )
        )

    reclaimed = reclaim_expired_lease(
        engine,
        action_key,
        new_lease_owner="worker-beta",
        lease_seconds=60,
    )

    assert reclaimed is True

    saved = get_action(engine, action_key)
    assert saved["status"] == "in_progress"

    with engine.connect() as connection:
        row = connection.execute(
            select(actions).where(actions.c.action_key == action_key)
        ).mappings().one()

    assert row["lease_owner"] == "worker-beta"


def test_active_lease_cannot_be_reclaimed(engine):
    from action_ledger import reclaim_expired_lease

    action_key = "action-reclaim-002"

    claim_action(
        engine,
        action_key,
        "inspect_service",
        {"incident_id": "INC-RECLAIM-002"},
        lease_owner="worker-alpha",
        lease_seconds=60,
    )

    reclaimed = reclaim_expired_lease(
        engine,
        action_key,
        new_lease_owner="worker-beta",
        lease_seconds=60,
    )

    assert reclaimed is False

    with engine.connect() as connection:
        row = connection.execute(
            select(actions).where(actions.c.action_key == action_key)
        ).mappings().one()

    assert row["lease_owner"] == "worker-alpha"

def test_other_worker_cannot_mark_action_uncertain(engine):
    action_key = "action-unauthorized-001"

    claim_action(
        engine,
        action_key,
        "inspect_service",
        {"incident_id": "INC-UNAUTHORIZED-001"},
        lease_owner="worker-alpha",
    )

    with pytest.raises(ValueError, match="does not own the lease"):
        mark_action_uncertain(
            engine,
            action_key,
            lease_owner="worker-beta",
        )

    saved = get_action(engine, action_key)
    assert saved["status"] == "in_progress"