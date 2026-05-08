param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$args = @(
    "tests/test_app_endpoints.py",
    "tests/test_coordinator.py",
    "tests/test_tools.py",
    "tests/test_bench_runner.py"
)

if ($Quiet) {
    python -m pytest @args -q
} else {
    python -m pytest @args -v
}
