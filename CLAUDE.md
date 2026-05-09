# AtlasOps — Claude Code Context

## What This Is
Multi-agent SRE incident response platform for the **AMD Developer Hackathon (lablab.ai)**.
Submission deadline: **May 10, 2026 — 7:00 PM UTC (12:30 AM IST May 11)**

## GCP Infrastructure (LIVE — costs money)
- **Project:** `cloudsre-v3-amd`
- **Cluster:** `atlasops` (was `cloudsre-v3`), GKE Standard, `us-central1`, 3× e2-standard-4
- **Grafana:** `http://136.119.60.129` (admin / cloudsre-admin)
- **Online Boutique:** `http://34.132.118.204`
- **Argo CD:** `https://34.122.132.237`
- **Cloud SQL:** `cloudsre-cart-db` (Postgres 15, `34.60.234.86`)
- **PubSub topics:** `cloudsre-checkout-events`, `cloudsre-alerts`
- **Prometheus:** `http://34.31.150.33:9090` (LoadBalancer — exposed May 9)
- **Alertmanager:** `http://34.135.158.165:9093` (LoadBalancer — exposed May 9)
- **Jaeger:** `http://104.198.218.251:16686` (LoadBalancer `jaeger-ui` service — exposed May 9)

## kubectl / gcloud
```powershell
$env:USE_GKE_GCLOUD_AUTH_PLUGIN = "True"
$env:PATH = "C:\Users\NSEIT\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin;$env:PATH"
$kubectl = "C:\Users\NSEIT\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\kubectl"
$gcloud  = "C:\Users\NSEIT\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$helm    = "C:\Users\NSEIT\AppData\Local\Microsoft\WinGet\Packages\Helm.Helm_Microsoft.Winget.Source_8wekyb3d8bbwe\windows-amd64\helm.exe"
```

## AMD MI300X Status
- Credits requested via AMD AI Developer Program (Gmail account)
- Also requested Fireworks AI credits as fallback
- Both arrive within 2 business days (~May 8-9)
- When credits land: spin up GPU Droplet on AMD Developer Cloud (GitHub account)

## LLM Backend
- Default: `BACKEND=vllm` → self-hosted on MI300X at `http://localhost:8000/v1`
- Fallback: `BACKEND=fireworks LLM_API_KEY=fw_xxxx` → Fireworks AI API
- Model: `Qwen/Qwen2.5-7B-Instruct` (agents) + `Qwen/Qwen2.5-72B-Instruct` (judge)

## Comms Integration
- `SLACK_WEBHOOK_URL` — Slack incoming webhook (optional; always logs locally to `data/slack_posts.jsonl`)
- `DISCORD_WEBHOOK_URL` — Discord channel webhook (optional; converts Slack payload to Discord embeds)
- UI polls `/slack/feed` every 5s and renders posts in `# incident-response` panel (bottom of right column)
- To get a Discord webhook: Server Settings → Integrations → Webhooks → New Webhook → Copy URL

## Key Files
- `agents/coordinator.py` — FastAPI app, webhook at `:9099/webhook`, SSE at `/stream`
- `agents/stream.py` — real-time thought streaming (SSE + 3s poll in dashboard)
- `agents/adversarial_designer.py` — 72B judge generates dynamic chaos scenarios
- `agents/judge.py` — scores agent trajectories
- `agents/tools/` — 20 real SRE tool wrappers
- `agents/prompts/` — triage / diagnosis / remediation / comms system prompts
- `bench/runner.py` — benchmark harness, generates adversarial scenarios before run
- `bench/chaos_manifests/` — sf-001..008, cs-001..005, mf-001..005, named_replays/
- `training/sft.py` — QLoRA SFT (TRL + PEFT, 4-bit, LoRA r=16)
- `training/grpo.py` — QLoRA GRPO (TRL GRPOTrainer)
- `dashboard.py` — Gradio Ops Console (HF Spaces deployment)
- `infra/setup.sh` — one-shot GCP provisioning (bash, needs Git Bash)
- `infra/values/` — Helm values for Prometheus, Jaeger, Argo CD, Chaos Mesh

## Chaos Manifest Fix
`spec.scheduler` was removed in Chaos Mesh v2 — already fixed in sf-001, discord, github manifests.

## Submission Checklist
- [ ] Public GitHub repo (`atlasops`)
- [ ] HF Space in AMD org (`huggingface.co/lablab-ai-amd-developer-hackathon`)
- [ ] Demo video ≤5 min MP4
- [ ] Slide deck PDF
- [ ] Cover image 16:9
- [ ] Build-in-Public: 2+ posts tagging `@AIatAMD` + `@lablab`
- [ ] Submit on lablab.ai before May 10 7PM UTC

## Tracks We're Entering
- Track 2 (Fine-Tuning on AMD) — primary
- Track 1 (AI Agents) — secondary
- HF Special Prize — publish Space in AMD org
- Build-in-Public — 2+ social posts
- Qwen Challenge — using Qwen2.5 throughout

## User
- Name: Hari Kishanth (harikishanth2006@gmail.com)
- Team: Da Big Three (lablab.ai)
- Student, India (UTC+5:30)
- AMD Developer Cloud: GitHub account
- AMD AI Developer Program: Gmail account (separate — important)
