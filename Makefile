PROJECT     ?= cloudsre-v3-amd
REGION      ?= us-central1
CLUSTER     ?= atlasops

# ── Cluster lifecycle ──────────────────────────────────────────────────────────
.PHONY: up down status

up:
	bash infra/setup.sh $(PROJECT) $(REGION) $(CLUSTER)

down:
	bash infra/teardown.sh $(PROJECT) $(REGION) $(CLUSTER)

status:
	kubectl get pods -A --context=gke_$(PROJECT)_$(REGION)_$(CLUSTER)

# ── Chaos injection ────────────────────────────────────────────────────────────
.PHONY: chaos chaos-reset

chaos:
	@if [ -z "$(SCENARIO)" ]; then echo "Usage: make chaos SCENARIO=sf-001"; exit 1; fi
	@MANIFEST=$$(find bench/chaos_manifests -name "$(SCENARIO).yaml" | head -1); \
	if [ -z "$$MANIFEST" ]; then echo "Scenario $(SCENARIO) not found"; exit 1; fi; \
	echo "Applying chaos: $$MANIFEST"; \
	kubectl apply -f $$MANIFEST

chaos-reset:
	kubectl delete podchaos,networkchaos,stresschaos,dnschaos,iochaos,timechaos --all -A 2>/dev/null || true

# ── Historical replays ─────────────────────────────────────────────────────────
replay-%:
	kubectl apply -f bench/chaos_manifests/named_replays/$*.yaml
	@echo "Replay $* triggered. Watch: make status"

# ── Agent runtime ──────────────────────────────────────────────────────────────
.PHONY: coordinator

coordinator:
	python agents/coordinator.py

# ── Benchmark ─────────────────────────────────────────────────────────────────
.PHONY: bench bench-baseline

bench:
	python bench/runner.py --model $(MODEL) --output bench/results/$(shell date +%Y%m%d_%H%M%S)

bench-baseline:
	python bench/runner.py --model checkpoints/cloudsre_v2_baseline --tag baseline_v2 \
	  --output bench/results/baseline_v2

# ── Training ───────────────────────────────────────────────────────────────────
.PHONY: sft grpo trajectories

trajectories:
	python training/generate_trajectories.py --output data/sft_corpus.jsonl

sft:
	python training/sft.py \
	  --model Qwen/Qwen2.5-7B-Instruct \
	  --data data/sft_corpus.jsonl \
	  --output checkpoints/sft_v3

grpo:
	python training/grpo.py \
	  --model checkpoints/sft_v3 \
	  --output checkpoints/grpo_v3 \
	  --tiers cascade,multi_fault,named_replays

# ── Dashboard ─────────────────────────────────────────────────────────────────
.PHONY: dashboard

dashboard:
	python dashboard.py

# ── Linting / tests ───────────────────────────────────────────────────────────
.PHONY: lint test release-gate smoke-e2e-local

lint:
	ruff check .

test:
	pytest tests/ -v

release-gate:
	python scripts/release_gate.py --strict --output docs/RELEASE_READINESS.md

smoke-e2e-local:
	pytest tests/test_app_endpoints.py tests/test_coordinator.py tests/test_tools.py tests/test_bench_runner.py -q
