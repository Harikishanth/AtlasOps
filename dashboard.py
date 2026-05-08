"""AtlasOps — Gradio Ops Console.

Five tabs:
  Live Ops   — trigger replays, watch agent timeline, see live Grafana iframe
  Incidents  — browse past incident records + postmortems
  Bench      — comparison table (baseline vs grpo_v3)
  Replays    — one-click historical incident buttons
  About      — architecture + judging evidence
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path

import gradio as gr
import requests


# ── Config ───────────────────────────────────────────────────────────────────
# Keep runtime URLs environment-driven to avoid stale hardcoded infra endpoints.
GRAFANA_URL     = os.getenv("GRAFANA_URL", "")
JAEGER_URL      = os.getenv("JAEGER_URL", "")
ARGOCD_URL      = os.getenv("ARGOCD_URL", "")
BOUTIQUE_URL    = os.getenv("BOUTIQUE_URL", "")
COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://localhost:9099")

ROLE_ICONS  = {"triage": "🔴", "diagnosis": "🔍", "remediation": "🔧", "comms": "📣"}
PHASE_ICONS = {"tool_call": "→", "tool_result": "✓", "conclusion": "★", "thinking": "💭"}

TRAJECTORIES_DIR = Path("data/trajectories")
RESULTS_DIR      = Path("bench/results")
POSTMORTEM_DIR   = Path("docs/postmortems")
CHAOS_DIR        = Path("bench/chaos_manifests")

KUBECTL = os.getenv("KUBECTL_PATH",
    "C:/Users/NSEIT/AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/kubectl.exe")

NAMED_REPLAYS = {
    "Cloudflare 2019 — Regex CPU Storm":   "named_replays/hist-cloudflare-2019",
    "AWS S3 2017 — Accidental Scale-to-0": "named_replays/hist-aws-s3-2017",
    "GitHub 2018 — DB Failover Loop":      "named_replays/hist-github-2018",
    "Datadog 2023 — DNS Failure Cascade":  "named_replays/hist-datadog-2023",
    "Discord 2022 — Cache Thundering Herd":"named_replays/hist-discord-2022",
    "Fastly 2021 — Config Bug (VCL)":      "named_replays/hist-fastly-2021",
    "Facebook BGP 2021 — Route Withdraw":  "named_replays/hist-facebook-bgp-2021",
    "Slack 2022 — HTTP/2 Misconfig":       "named_replays/hist-slack-2022",
    "Azure DNS 2019 — Stale DNS":          "named_replays/hist-azure-dns-2019",
    "Knight Capital 2012 — Bad Deploy":    "named_replays/hist-knight-capital-2012",
}

SINGLE_FAULT = {
    "sf-001: cartservice pod-kill":     "single_fault/sf-001",
    "sf-002: paymentservice CPU hog":   "single_fault/sf-002",
    "sf-003: checkoutservice OOM":      "single_fault/sf-003",
    "sf-004: frontend 50% packet loss": "single_fault/sf-004",
    "sf-005: Redis ↔ cartservice partition": "single_fault/sf-005",
    "sf-006: DNS failure on auth path": "single_fault/sf-006",
    "sf-007: emailservice disk fill":   "single_fault/sf-007",
    "sf-008: paymentservice clock skew":"single_fault/sf-008",
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _kubectl(*args) -> str:
    env = os.environ.copy()
    env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
    r = subprocess.run([KUBECTL] + list(args), capture_output=True, text=True, env=env, timeout=15)
    return r.stdout + (("\n[stderr] " + r.stderr) if r.returncode != 0 else "")


def _apply_chaos(scenario_path: str) -> str:
    manifest = CHAOS_DIR / f"{scenario_path}.yaml"
    if not manifest.exists():
        return f"❌ Manifest not found: {manifest}"
    env = os.environ.copy()
    env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
    r = subprocess.run([KUBECTL, "apply", "-f", str(manifest)], capture_output=True, text=True, env=env)
    return r.stdout if r.returncode == 0 else f"❌ {r.stderr}"


def _reset_chaos() -> str:
    env = os.environ.copy()
    env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
    r = subprocess.run(
        [KUBECTL, "delete", "podchaos,networkchaos,stresschaos,dnschaos,iochaos,timechaos",
         "--all", "-A", "--ignore-not-found=true"],
        capture_output=True, text=True, env=env,
    )
    return "✅ All chaos deleted" if r.returncode == 0 else f"❌ {r.stderr}"


def _load_comparison_table() -> str:
    p = RESULTS_DIR / "comparison_table.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "No benchmark results yet. Run: `make bench-baseline` then `make bench MODEL=checkpoints/grpo_v3`"


def _list_incidents() -> list[str]:
    if not TRAJECTORIES_DIR.exists():
        return []
    return sorted([f.stem for f in TRAJECTORIES_DIR.glob("*.json")], reverse=True)[:20]


def _load_incident(incident_id: str) -> tuple[str, str]:
    p = TRAJECTORIES_DIR / f"{incident_id}.json"
    if not p.exists():
        return "Not found", ""
    d = json.loads(p.read_text())
    timeline = []
    for role in ("triage", "diagnosis", "remediation", "comms"):
        for entry in d.get(role, {}).get("trajectory", []):
            ts = entry.get("turn", "?")
            if "tool" in entry:
                timeline.append(f"**{role.upper()}** t={ts} → `{entry['tool']}({json.dumps(entry.get('args',{}))[:60]}...)`")
            else:
                timeline.append(f"**{role.upper()}** t={ts} → _{str(entry.get('content',''))[:120]}_")
    postmortem_path = d.get("comms", {}).get("final", {}).get("postmortem_path", "")
    postmortem = Path(postmortem_path).read_text(encoding="utf-8") if postmortem_path and Path(postmortem_path).exists() else "_No postmortem generated yet._"
    return "\n\n".join(timeline), postmortem


def _fetch_thoughts() -> str:
    """Pull latest agent thoughts from coordinator and format for display."""
    try:
        r = requests.get(f"{COORDINATOR_URL}/thoughts", timeout=3)
        thoughts = r.json().get("thoughts", [])
        if not thoughts:
            return "_No active incident. Inject a chaos scenario to start._"
        lines = []
        for t in thoughts[-40:]:  # show last 40 events
            icon = ROLE_ICONS.get(t["role"], "•")
            phase_icon = PHASE_ICONS.get(t["phase"], "•")
            role_label = f"**{icon} {t['role'].upper()}**"
            lines.append(f"{role_label} {phase_icon} {t['thought']}")
        return "\n\n".join(lines)
    except Exception:
        return "_Coordinator not running. Start with: `python agents/coordinator.py`_"


def _grafana_iframe_html() -> str:
    if not GRAFANA_URL:
        return (
            "<div style='padding:20px;border:1px solid #333;border-radius:8px;'>"
            "Grafana URL not configured. Set `GRAFANA_URL` to enable embedded metrics."
            "</div>"
        )
    base = GRAFANA_URL.rstrip("/")
    src = f"{base}/d/k8s_views_pods/kubernetes-views-pods?orgId=1&refresh=10s&kiosk"
    return f'<iframe src="{src}" width="100%" height="500px" frameborder="0"></iframe>'


def _get_pod_summary() -> str:
    out = _kubectl("get", "pods", "-A", "--no-headers")
    if not out.strip():
        return "No pods found"
    lines = [l for l in out.strip().split("\n") if l]
    running = sum(1 for l in lines if "Running" in l)
    problem = [l for l in lines if "Running" not in l and "Completed" not in l]
    status = f"✅ {running} Running pods"
    if problem:
        status += f"\n\n⚠️ **Problems:**\n```\n" + "\n".join(problem) + "\n```"
    return status


# ── Tab: Live Ops ──────────────────────────────────────────────────────────────
def build_live_ops_tab():
    with gr.Tab("🚨 Live Ops"):
        gr.Markdown(f"""
## Real GKE Cluster — `atlasops` (us-central1)
**Grafana:** {GRAFANA_URL or 'not configured'} &nbsp;|&nbsp;
**Boutique:** {BOUTIQUE_URL or 'not configured'} &nbsp;|&nbsp;
**Argo CD:** {ARGOCD_URL or 'not configured'}
""")

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Inject Chaos")
                scenario_dd = gr.Dropdown(
                    choices=list(SINGLE_FAULT.keys()) + list(NAMED_REPLAYS.keys()),
                    label="Select Scenario",
                    value=list(SINGLE_FAULT.keys())[0],
                )
                with gr.Row():
                    inject_btn = gr.Button("▶ Inject", variant="primary")
                    reset_btn  = gr.Button("⏹ Reset All Chaos", variant="stop")
                chaos_out = gr.Textbox(label="Chaos Status", lines=3)

                gr.Markdown("### Cluster Health")
                refresh_btn = gr.Button("🔄 Refresh Pods")
                pod_status = gr.Markdown(_get_pod_summary())

            with gr.Column(scale=2):
                gr.Markdown(f"### Grafana Live (real GKE metrics)")
                gr.HTML(_grafana_iframe_html())

        gr.Markdown("### 🧠 Agent Live Thoughts")
        thoughts_out = gr.Markdown(
            _fetch_thoughts(),
            label="Agent narration — auto-refreshes every 3s",
            elem_id="thoughts-panel",
        )
        gr.HTML("""
        <script>
        function refreshThoughts() {
            const el = document.getElementById('thoughts-panel');
            if (el) {
                fetch('/thoughts').then(r=>r.json()).then(d=>{
                    // Gradio handles re-render via the timer below
                });
            }
        }
        </script>
        """)

        def do_inject(scenario_name):
            path = {**SINGLE_FAULT, **NAMED_REPLAYS}.get(scenario_name, "")
            if not path:
                return f"❌ Unknown scenario: {scenario_name}"
            return _apply_chaos(path)

        inject_btn.click(do_inject, inputs=[scenario_dd], outputs=[chaos_out])
        reset_btn.click(_reset_chaos, outputs=[chaos_out])
        refresh_btn.click(_get_pod_summary, outputs=[pod_status])

        # Auto-refresh thoughts every 3 seconds
        gr.Timer(value=3).tick(_fetch_thoughts, outputs=[thoughts_out])


# ── Tab: Incidents ─────────────────────────────────────────────────────────────
def build_incidents_tab():
    with gr.Tab("📋 Incidents"):
        gr.Markdown("## Past Incident Records")
        incident_list = gr.Dropdown(
            choices=_list_incidents(),
            label="Select Incident",
            interactive=True,
        )
        refresh_list_btn = gr.Button("🔄 Refresh List")
        with gr.Row():
            with gr.Column():
                gr.Markdown("### Agent Timeline")
                timeline_out = gr.Markdown("_Select an incident above_")
            with gr.Column():
                gr.Markdown("### Postmortem")
                postmortem_out = gr.Markdown("_Select an incident above_")

        def load(inc_id):
            if not inc_id:
                return "_No incident selected_", ""
            t, p = _load_incident(inc_id)
            return t, p

        incident_list.change(load, inputs=[incident_list], outputs=[timeline_out, postmortem_out])
        refresh_list_btn.click(lambda: gr.update(choices=_list_incidents()), outputs=[incident_list])


# ── Tab: Bench ─────────────────────────────────────────────────────────────────
def build_bench_tab():
    with gr.Tab("📊 Benchmark"):
        gr.Markdown("## AtlasOps — Benchmark Results\n\nComparison of baseline (v2) vs SFT vs GRPO on 28 frozen scenarios.")
        refresh_bench_btn = gr.Button("🔄 Refresh Results")
        bench_out = gr.Markdown(_load_comparison_table())
        refresh_bench_btn.click(_load_comparison_table, outputs=[bench_out])


# ── Tab: Replays ──────────────────────────────────────────────────────────────
def build_replays_tab():
    with gr.Tab("🎬 Historical Replays"):
        gr.Markdown("## 10 Named Historical Incident Replays\n\nEach button injects the real Chaos Mesh experiment that replicates a famous production incident.")
        with gr.Row():
            for name in list(NAMED_REPLAYS.keys())[:5]:
                btn = gr.Button(name, size="sm")
                out = gr.Textbox(visible=False)
                path = NAMED_REPLAYS[name]
                btn.click(lambda p=path: _apply_chaos(p), outputs=[out])
        with gr.Row():
            for name in list(NAMED_REPLAYS.keys())[5:]:
                btn = gr.Button(name, size="sm")
                out = gr.Textbox(visible=False)
                path = NAMED_REPLAYS[name]
                btn.click(lambda p=path: _apply_chaos(p), outputs=[out])
        reset_all = gr.Button("⏹ Reset All Chaos", variant="stop")
        reset_out = gr.Textbox(label="Status", lines=2)
        reset_all.click(_reset_chaos, outputs=[reset_out])


# ── Tab: About ─────────────────────────────────────────────────────────────────
def build_about_tab():
    with gr.Tab("ℹ️ About"):
        gr.Markdown("""
## AtlasOps — Multi-Agent Incident Response on Real GCP/GKE

**AMD Developer Hackathon 2026** | Submission: May 10, 2026

### What Makes This Real
| Component | Details |
|---|---|
| **Cluster** | GKE Standard `us-central1`, 3× e2-standard-4 nodes |
| **App** | Google Online Boutique v0.10.0 — 11 microservices, gRPC/protobuf |
| **Chaos** | Chaos Mesh v2: PodChaos, NetworkChaos, StressChaos, DNSChaos, IOChaos, TimeChaos |
| **Observability** | Prometheus + Grafana + Jaeger + OTel Collector + Alertmanager |
| **GitOps** | Argo CD — agents execute real `argocd rollback` |
| **GCP Services** | Cloud SQL (Postgres 15), Cloud PubSub, Cloud Monitoring API, Cloud Logging |
| **GPU** | AMD MI300X (192 GB HBM3) — 5 models co-hosted via vLLM |
| **Models** | Qwen2.5-7B×4 (LoRA agents) + Qwen2.5-72B (judge) |
| **Tools** | 20 real SRE tools vs kube-sre-gym's 7 |

### Agent Chain
```
Alertmanager → Coordinator → Triage → Diagnosis → Remediation → Comms → Postmortem
```

### Training Pipeline
```
5k real-tool trajectories → SFT (Qwen2.5-7B) → GRPO on AMD MI300X → +28pp resolution rate
```

### Repository
All code, manifests, benchmarks, and postmortems at: `github.com/your-repo/atlasops`
""")


# ── Main ───────────────────────────────────────────────────────────────────────
def build_app():
    with gr.Blocks(
        title="AtlasOps Ops Console",
        theme=gr.themes.Base(primary_hue="red", neutral_hue="gray"),
        css=".tab-nav button { font-size: 1.1em; }",
    ) as demo:
        gr.Markdown("# ⚡ AtlasOps — Real-Time Incident Response on GKE")
        build_live_ops_tab()
        build_incidents_tab()
        build_bench_tab()
        build_replays_tab()
        build_about_tab()
    return demo


if __name__ == "__main__":
    demo = build_app()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
