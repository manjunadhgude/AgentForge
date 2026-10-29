
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from action_ledger import claim_action, initialize_ledger


@pytest.fixture
def postgres_engine():
    password = os.environ.get("AGENTFORGE_DB_PASSWORD")
    if not password:
        pytest.skip("AGENTFORGE_DB_PASSWORD is not set")

    database_url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ.get("AGENTFORGE_DB_USER", "agentforge"),
        password=password,
        host=os.environ.get("AGENTFORGE_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("AGENTFORGE_DB_PORT", "5432")),
        database=os.environ.get("AGENTFORGE_DB_NAME", "agentforge"),
    )

    engine = create_engine(
        database_url,
        pool_size=2,
        max_overflow=0,
    )

    try:
        initialize_ledger(engine)
        yield engine
    finally:
        engine.dispose()


def test_two_workers_cannot_claim_the_same_action(postgres_engine):
    action_key = f"concurrency-test-{uuid4().hex}"
    request = {"incident_id": "INC-CONCURRENT-001"}
    barrier = Barrier(2)

    def attempt_claim():
        barrier.wait(timeout=10)
        return claim_action(
            postgres_engine,
            action_key,
            "inspect_service",
            request,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(attempt_claim),
            executor.submit(attempt_claim),
        ]
        results = [future.result(timeout=15) for future in futures]

    assert sum(result["claimed"] for result in results) == 1
    assert sum(not result["claimed"] for result in results) == 1
    assert {result["status"] for result in results} == {"in_progress"}
