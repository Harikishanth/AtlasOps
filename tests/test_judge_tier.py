from agents.judge import infer_tier_from_alert


def test_infer_tier_from_scenario_paths():
    assert infer_tier_from_alert({"scenario_id": "single_fault/sf-003"}) == "single_fault"
    assert infer_tier_from_alert({"scenario_id": "cascade/cs-002"}) == "cascade"
    assert infer_tier_from_alert({"scenario_id": "multi_fault/mf-001"}) == "multi_fault"
    assert infer_tier_from_alert({"scenario_id": "named_replays/hist-github-2018"}) == "named_replays"
    assert infer_tier_from_alert({"scenario_id": "adversarial/adv-001"}) == "adversarial"
    assert infer_tier_from_alert({"commonLabels": {"alertname": "x"}}) == "single_fault"
