# AtlasOps Release Readiness

- Overall: **FAIL**
- Critical failures: **2**
- Warnings: **0**

## Checks
- [FAIL] `Required artifacts` (critical) - Missing: bench\results\comparison_table.md
- [PASS] `Chaos manifest count (single_fault)` (critical) - Expected 8, found 8.
- [PASS] `Chaos manifest count (cascade)` (critical) - Expected 5, found 5.
- [PASS] `Chaos manifest count (multi_fault)` (critical) - Expected 5, found 5.
- [PASS] `Chaos manifest count (named_replays)` (critical) - Expected 10, found 10.
- [PASS] `Difficulty tiers declared` (critical) - All five required tiers are declared in runtime config.
- [PASS] `Tier scenario pool coverage` (advisory) - Scenario pools include all required tiers or intentionally map tiers elsewhere.
- [PASS] `/config endpoint` (critical) - Configured correctly.
- [PASS] `Static UI dynamic config` (critical) - Configured correctly.
- [FAIL] `Benchmark output sanity` (critical) - comparison_table.md missing or empty.

## Blockers
- `Required artifacts` - Missing: bench\results\comparison_table.md
- `Benchmark output sanity` - comparison_table.md missing or empty.

