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


def test_duplicate_delivery_executes_baseline_each_time_and_replays_agentforge_result():
    scenario = run_comparison()["scenarios"]["duplicate_delivery_replay"]

    assert scenario["baseline"]["attempts"] == 5
    assert scenario["baseline"]["handler_invocations"] == 5
    assert scenario["baseline"]["simulated_side_effects"] == 5
    assert scenario["agentforge"]["handler_invocations"] == 1
    assert scenario["agentforge"]["simulated_side_effects"] == 1
    assert scenario["baseline"]["caller_visible_successes"] == 5
    assert scenario["agentforge"]["caller_visible_successes"] == 5
    assert scenario["assertions"]["per_delivery_results_equivalent"] is True
    assert scenario["assertions"]["remaining_deliveries_replayed"] is True


def test_ambiguous_outcome_executes_baseline_twice_but_blocks_agentforge_retry():
    scenario = run_comparison()["scenarios"]["ambiguous_outcome"]

    assert scenario["baseline"]["attempts"] == 2
    assert scenario["baseline"]["handler_invocations"] == 2
    assert scenario["baseline"]["simulated_side_effects"] == 2
    assert scenario["baseline"]["caller_visible_successes"] == 0
    assert scenario["assertions"]["baseline_consumed_schedule_in_order"] is True
    assert scenario["assertions"]["baseline_consumed_all_schedule_events"] is True
    assert scenario["agentforge"]["attempts"] == 2
    assert scenario["agentforge"]["handler_invocations"] == 1
    assert scenario["agentforge"]["simulated_side_effects"] == 1
    assert scenario["agentforge"]["caller_visible_successes"] == 0
    assert scenario["agentforge"]["state"] == "uncertain"
    assert scenario["assertions"]["agentforge_blocks_second_execution"] is True
