from benchmarks.run_execution_comparison import run_comparison


def test_matched_reliability_scenarios_pass_all_invariants():
    report = run_comparison()

    assert report["all_invariants_passed"] is True
    assert set(report["scenarios"]) == {
        "normal_execution",
        "recoverable_transient_failure",
        "duplicate_delivery_replay",
        "ambiguous_outcome",
    }


def test_transient_failure_uses_same_bounded_schedule():
    scenario = run_comparison()["scenarios"]["recoverable_transient_failure"]

    assert scenario["failure_schedule"] == [
        "fail_before_side_effect",
        "succeed",
    ]
    assert scenario["retry_configuration"]["max_attempts"] == 3
    assert scenario["baseline"]["attempts"] == 2
    assert scenario["agentforge"]["attempts"] == 2
    assert scenario["baseline"]["handler_invocations"] == 1
    assert scenario["agentforge"]["handler_invocations"] == 1


def test_duplicate_delivery_reuses_saved_result():
    scenario = run_comparison()["scenarios"]["duplicate_delivery_replay"]

    assert scenario["baseline"]["handler_invocations"] == 5
    assert scenario["agentforge"]["handler_invocations"] == 1
    assert scenario["assertions"]["remaining_deliveries_replayed"] is True


def test_ambiguous_outcome_blocks_agentforge_blind_reexecution():
    scenario = run_comparison()["scenarios"]["ambiguous_outcome"]

    assert scenario["baseline"]["handler_invocations"] == 2
    assert scenario["agentforge"]["handler_invocations"] == 1
    assert scenario["agentforge"]["state"] == "uncertain"
    assert scenario["assertions"]["agentforge_blocks_second_execution"] is True
