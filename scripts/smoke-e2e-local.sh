#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-verbose}"

TESTS=(
  "tests/test_app_endpoints.py"
  "tests/test_coordinator.py"
  "tests/test_tools.py"
  "tests/test_bench_runner.py"
)

if [[ "$MODE" == "quiet" ]]; then
  python -m pytest "${TESTS[@]}" -q
else
  python -m pytest "${TESTS[@]}" -v
fi
