"""Validate all Chaos Mesh manifests are syntactically correct YAML
and contain required fields."""

from pathlib import Path
import pytest
import yaml


MANIFESTS_DIR = Path(__file__).parent.parent / "bench" / "chaos_manifests"

REQUIRED_KINDS = {
    "PodChaos", "NetworkChaos", "StressChaos", "DNSChaos",
    "IOChaos", "TimeChaos",
}


def collect_manifests():
    return list(MANIFESTS_DIR.rglob("*.yaml"))


@pytest.mark.parametrize("manifest_path", collect_manifests())
def test_manifest_is_valid_yaml(manifest_path):
    content = manifest_path.read_text(encoding="utf-8")
    docs = list(yaml.safe_load_all(content))
    assert len(docs) >= 1, f"{manifest_path} produced no YAML documents"


@pytest.mark.parametrize("manifest_path", collect_manifests())
def test_manifest_has_required_fields(manifest_path):
    content = manifest_path.read_text(encoding="utf-8")
    for doc in yaml.safe_load_all(content):
        if doc is None:
            continue
        # Skip non-chaos resources (e.g. Argo CD Application, Deployment)
        if doc.get("kind") not in REQUIRED_KINDS:
            continue
        assert "apiVersion" in doc, f"Missing apiVersion in {manifest_path}"
        assert "metadata" in doc, f"Missing metadata in {manifest_path}"
        assert "spec" in doc, f"Missing spec in {manifest_path}"
        assert "selector" in doc["spec"], f"Missing spec.selector in {manifest_path}"


@pytest.mark.parametrize("manifest_path", collect_manifests())
def test_manifest_no_deprecated_scheduler(manifest_path):
    """spec.scheduler was removed in Chaos Mesh v2 — must not be present."""
    content = manifest_path.read_text(encoding="utf-8")
    for doc in yaml.safe_load_all(content):
        if doc is None or doc.get("kind") not in REQUIRED_KINDS:
            continue
        spec = doc.get("spec", {})
        assert "scheduler" not in spec, (
            f"{manifest_path} uses deprecated spec.scheduler — "
            f"remove it (Chaos Mesh v2 uses spec.duration instead)"
        )


def test_all_tiers_present():
    tiers = {p.parent.name for p in collect_manifests()}
    assert "single_fault" in tiers
    assert "cascade" in tiers
    assert "named_replays" in tiers
    assert "multi_fault" in tiers
    assert "adversarial" in tiers


def test_adversarial_templates_present():
    adv_dir = MANIFESTS_DIR / "adversarial"
    templates = list(adv_dir.glob("adv-*.yaml"))
    assert len(templates) >= 1, "Frozen adv-*.yaml templates should exist for UI + curriculum"


def test_single_fault_count():
    sf = list((MANIFESTS_DIR / "single_fault").glob("*.yaml"))
    assert len(sf) == 8, f"Expected 8 single-fault scenarios, got {len(sf)}"


def test_cascade_count():
    cs = list((MANIFESTS_DIR / "cascade").glob("*.yaml"))
    assert len(cs) == 5, f"Expected 5 cascade scenarios, got {len(cs)}"


def test_named_replays_count():
    nr = list((MANIFESTS_DIR / "named_replays").glob("*.yaml"))
    assert len(nr) == 10, f"Expected 10 named replays, got {len(nr)}"


def test_multi_fault_count():
    mf = list((MANIFESTS_DIR / "multi_fault").glob("*.yaml"))
    assert len(mf) == 5, f"Expected 5 multi-fault scenarios, got {len(mf)}"
