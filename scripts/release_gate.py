"""Generate a release-readiness gate report for AtlasOps.

The goal is to provide a single command that validates core shipping evidence
before hackathon submission and emits a human-readable markdown report.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "RELEASE_READINESS.md"


@dataclass
class CheckResult:
    name: str
    status: str  # PASS | FAIL | WARN
    details: str
    critical: bool = True


def _exists(path: Path) -> bool:
    return path.exists()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def check_artifact_presence() -> list[CheckResult]:
    required = [
        ROOT / "docs" / "AMD_FINAL_DELIVERY_SCORECARD_AND_REWARD_SPEC.md",
        ROOT / "docs" / "MI300X_EVIDENCE.md",
        ROOT / "bench" / "results" / "comparison_table.md",
        ROOT / "tests" / "test_app_endpoints.py",
        ROOT / "tests" / "test_bench_runner.py",
        ROOT / "tests" / "test_chaos_manifests.py",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not _exists(p)]
    if missing:
        return [CheckResult("Required artifacts", "FAIL", f"Missing: {', '.join(missing)}", True)]
    return [CheckResult("Required artifacts", "PASS", "All required docs/results/tests present.", True)]


def check_chaos_manifest_inventory() -> list[CheckResult]:
    expected = {
        "single_fault": 8,
        "cascade": 5,
        "multi_fault": 5,
        "named_replays": 10,
    }
    results: list[CheckResult] = []
    for tier, count in expected.items():
        actual = len(list((ROOT / "bench" / "chaos_manifests" / tier).glob("*.yaml")))
        if actual != count:
            results.append(
                CheckResult(
                    f"Chaos manifest count ({tier})",
                    "FAIL",
                    f"Expected {count}, found {actual}.",
                    True,
                )
            )
        else:
            results.append(
                CheckResult(
                    f"Chaos manifest count ({tier})",
                    "PASS",
                    f"Expected {count}, found {actual}.",
                    True,
                )
            )
    return results


def check_runtime_tiers() -> list[CheckResult]:
    runtime_text = _read_text(ROOT / "config" / "runtime.py")
    expected_tiers = ["warmup", "single_fault", "cascade", "multi_fault", "adversarial"]
    missing_from_speed = [t for t in expected_tiers if f'"{t}"' not in runtime_text]
    base = []
    if missing_from_speed:
        base.append(
            CheckResult(
                "Difficulty tiers declared",
                "FAIL",
                "Missing tier labels in runtime config: " + ", ".join(missing_from_speed),
                True,
            )
        )
    else:
        base.append(
            CheckResult(
                "Difficulty tiers declared",
                "PASS",
                "All five required tiers are declared in runtime config.",
                True,
            )
        )

    # Advisory: warmup/adversarial scenario pools are often omitted accidentally.
    advisory_missing = [
        t for t in ("warmup", "adversarial") if f'SCENARIOS_BY_TIER = {{' in runtime_text and f'"{t}":' not in runtime_text
    ]
    if advisory_missing:
        base.append(
            CheckResult(
                "Tier scenario pool coverage",
                "WARN",
                "No explicit SCENARIOS_BY_TIER entries for: " + ", ".join(advisory_missing),
                False,
            )
        )
    else:
        base.append(
            CheckResult(
                "Tier scenario pool coverage",
                "PASS",
                "Scenario pools include all required tiers or intentionally map tiers elsewhere.",
                False,
            )
        )
    return base


def check_ui_runtime_config() -> list[CheckResult]:
    app_text = _read_text(ROOT / "app.py")
    static_text = _read_text(ROOT / "static" / "index.html")
    checks = [
        ("/config endpoint", '@app.get("/config")' in app_text),
        ("Static UI dynamic config", "fetch('/config'" in static_text),
    ]
    out: list[CheckResult] = []
    for name, ok in checks:
        out.append(
            CheckResult(
                name,
                "PASS" if ok else "FAIL",
                "Configured correctly." if ok else "Missing expected runtime-config wiring.",
                True,
            )
        )
    return out


def check_benchmark_columns() -> list[CheckResult]:
    table = _read_text(ROOT / "bench" / "results" / "comparison_table.md")
    if not table:
        return [CheckResult("Benchmark output sanity", "FAIL", "comparison_table.md missing or empty.", True)]
    expected_tokens = ["avg_reward_contract", "avg_penalty", "unsafe_actions", "false_resolution", "hallucinated_evidence"]
    missing = [t for t in expected_tokens if t not in table]
    if missing:
        return [
            CheckResult(
                "Benchmark output sanity",
                "WARN",
                "Missing newer anti-gaming columns: " + ", ".join(missing),
                False,
            )
        ]
    return [CheckResult("Benchmark output sanity", "PASS", "Anti-gaming benchmark columns present.", False)]


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    results.extend(check_artifact_presence())
    results.extend(check_chaos_manifest_inventory())
    results.extend(check_runtime_tiers())
    results.extend(check_ui_runtime_config())
    results.extend(check_benchmark_columns())
    return results


def render_report(results: list[CheckResult]) -> str:
    critical_failures = [r for r in results if r.critical and r.status == "FAIL"]
    warnings = [r for r in results if r.status == "WARN"]
    overall = "PASS" if not critical_failures else "FAIL"
    lines = [
        "# AtlasOps Release Readiness",
        "",
        f"- Overall: **{overall}**",
        f"- Critical failures: **{len(critical_failures)}**",
        f"- Warnings: **{len(warnings)}**",
        "",
        "## Checks",
    ]
    for r in results:
        icon = "PASS" if r.status == "PASS" else ("FAIL" if r.status == "FAIL" else "WARN")
        gate = "critical" if r.critical else "advisory"
        lines.append(f"- [{icon}] `{r.name}` ({gate}) - {r.details}")
    lines.append("")
    if critical_failures:
        lines.append("## Blockers")
        for r in critical_failures:
            lines.append(f"- `{r.name}` - {r.details}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AtlasOps release readiness gate.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Markdown report output path.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero on critical failures.")
    args = parser.parse_args()

    results = run_checks()
    report = render_report(results)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote release readiness report: {output_path}")
    critical_failures = [r for r in results if r.critical and r.status == "FAIL"]
    if args.strict and critical_failures:
        print("Release gate failed (critical checks).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
