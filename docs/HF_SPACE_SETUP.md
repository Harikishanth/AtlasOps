# Hugging Face Spaces — wired 7B agents + 72B judge

## Hackathon Space URL (avoid 404)

The LabLab org Space slug uses a **hyphen**: **`atlas-ops`**, not `atlasops`.

| What | URL |
|------|-----|
| Space repo (clone / git push) | `https://huggingface.co/spaces/lablab-ai-amd-developer-hackathon/atlas-ops` |
| Embedded app (typical) | `https://lablab-ai-amd-developer-hackathon-atlas-ops.hf.space` |
| Health check | Same host as app + `/health` (not the repo `.git` URL) |

If you **duplicate or rename** the Space, replace `atlas-ops` everywhere below with your actual slug.

**Git remote example**

```bash
git remote remove lablab 2>/dev/null
git remote add lablab https://huggingface.co/spaces/lablab-ai-amd-developer-hackathon/atlas-ops
git push lablab main
```

**Secrets:** set **`ATLASOPS_PUBLIC_BASE_URL`** to the **app** URL (no trailing slash), e.g. `https://lablab-ai-amd-developer-hackathon-atlas-ops.hf.space`, so approval / Discord hints use the Space the judges open — not localhost and not an old slug.

---

AtlasOps speaks **two** OpenAI-compatible HTTP endpoints:

| Role | Env vars | Typical model id |
|------|-----------|-------------------|
| **Incident agents** (triage→comms) | `VLLM_BASE`, `AGENT_MODEL`, token | Your merged 7B on Hub **or** `Qwen/Qwen2.5-7B-Instruct` |
| **Judge** (scores responses; benchmarks + optional live ribbon) | `JUDGE_URL`, `JUDGE_MODEL`, token | Smaller HF model if 72B is blocked on quota |

## One-switch setup on the Space root

Configure **Space → Settings → Variables and secrets**:

1. **`HF_TOKEN`** — your HF access token (**read** plus **Inference** / **fine-grained Inference** permission if you use Router).
2. **`ATLASOPS_USE_HF_INFERENCE`** = `1`

This activates `config/hf_space_env.py`: it copies `HF_TOKEN` into `LLM_API_KEY` and `JUDGE_API_KEY`, and points both routers at **`https://router.huggingface.co/v1`** when you were still using localhost placeholders.

Optional override:

```
HF_INFERENCE_BASE=https://router.huggingface.co/v1
```

## Model IDs agents will call

Required:

```
AGENT_MODEL=<your-namespace/your-atlasops-merged-7b>
JUDGE_MODEL=Qwen/Qwen2.5-72B-Instruct-AWQ
```

(or any Hub model Router actually serves under your billing tier)

72B AWQ often needs a **paid** Inference allotment or **dedicated Inference Endpoint**.  
If Router returns 429/403 on 72B, set for example **`JUDGE_MODEL=Qwen/Qwen2.5-32B-Instruct`** temporarily — AtlasOps keeps working.

## Putting your GRPO weights on Hugging Face (7B)

The coordinator sends **only** a `model` string (no silent LoRA layer). Serving options:

1. **Merge LoRA locally** into the base checkpoint, upload the merged weights to `your-org/atlasops-7b-grpo`, set `AGENT_MODEL` to that repo (see `training/merge_lora_for_hub.py` after `pip install -e ".[train]"`).
2. **Self-hosted vLLM + `--enable-lora`** on AMD hardware (not HF Space CPU) — would require coordinator changes to attach LoRA per request unless you bake merged weights yourself.

For most hackathon demos **merged Hub model + Router** is the least painful.

## Live judge inside the Ops UI

When `ATLASOPS_USE_HF_INFERENCE=1`, the coordinator fires **one judge call after comms**, and the timeline prints the score (`judge_trajectory` tool line).

Explicit flags:

```
ATLASOPS_LIVE_JUDGE=1   # force ON
ATLASOPS_LIVE_JUDGE=0   # force OFF even with HF inference pack
```

Local MI300x with `JUDGE_URL=http://localhost:8001/v1`: keep **`ATLASOPS_USE_HF_INFERENCE` unset**, set **`ATLASOPS_LIVE_JUDGE=1`** if you still want judge lines in Grafana.

## Health checks after deploy

- `GET https://<space>/health` — agent + judge **model names** + bases (inspect JSON).
- `GET https://<space>/api/health` — coordinator copy with `live_judge` Boolean.

Neither endpoint prints raw tokens.

After redeploy with the bundled UI, the **footer bar** polls `/health` and shows **`Discord webhook ✓`** or **`✗ add DISCORD_WEBHOOK_URL`** so you know whether `DISCORD_WEBHOOK_URL` reached the Space (no webhook URL is ever rendered).

## Summary checklist

```
HF_TOKEN=<secret>
ATLASOPS_USE_HF_INFERENCE=1
AGENT_MODEL=your-org/your-trained-merged-7b
JUDGE_MODEL=Qwen/Qwen2.5-72B-Instruct-AWQ    # or a smaller HF model Router allows
BACKEND=openai                                 # optional; bootstrap sets default when ATLASOPS_USE_HF_INFERENCE=1
```

Redeploy the Space; trigger chaos from the sidebar and confirm timeline shows both tool calls (`judge` / `judge_trajectory`) and agent turns.

## Space has no kubeconfig (Pod Kill returns 500)

The UI’s **Inject** endpoint runs `kubectl apply` on chaos manifests. Typical HF Space containers **do not** have credentials to your GKE API server, so you will see **`POST /inject` → 500** in logs and the coordinator never starts.

Set this **Space variable** so inject **skips** kubectl but still schedules the incident pipeline (reads **live** Alertmanager after a short delay):

```
ATLASOPS_SKIP_KUBECTL_INJECT=1
```

Real fault injection still requires a reachable cluster from **somewhere** that has kubeconfig (CI, laptop, or another service). For a public demo, you can rely on **already-firing** alerts in Alertmanager or webhook-driven incidents.

---

## Discord (why nothing appears in your server)

AtlasOps does **not** use a Discord “bot” that shows online in the member list. It posts through an **Incoming Webhook** URL.

1. Discord → your server → **Server Settings** → **Integrations** → **Webhooks** → **New Webhook** → pick `#general` (or a channel) → copy **Webhook URL**.
2. In HF Space **Secrets**, add **`DISCORD_WEBHOOK_URL`** = that URL (same as `agents/tools/comms.py` expects).
3. **Every scenario/incident pipeline** triggers **one automatic Discord embed** when `DISCORD_WEBHOOK_URL` is set (coordinator fires this in `finally` after each `handle_incident`, including demo injects — independent of whether the LLM calls `slack_post_update`). Approval + closure + this ping can **burst** Discord’s webhook quota (**HTTP 429**); delivery now **retries** with `Retry-After`. Disable noise with **`ATLASOPS_DISCORD_EVERY_RUN_PING=0`**. Extra detail still appears when **comms** uses `slack_post_update`. If Discord is still empty after a run finishes, check Space logs and **`VLLM_BASE`** (stalled pipelines never reach `finally`).

Optional: **`SLACK_WEBHOOK_URL`** for Slack in parallel; both can be set.

---

## Final hour — submission checklist (do in order)

1. **Right Space URL** — Use **`lablab-ai-amd-developer-hackathon/atlas-ops`** (hyphen). Wrong slug → **404**. Push: `git push https://huggingface.co/spaces/lablab-ai-amd-developer-hackathon/atlas-ops main` (or add `lablab` remote; see section at top).

2. **Build green** — Space → **Logs** → build finished, app listening on **7860**.

3. **Secrets sanity**
   - **`VLLM_BASE`** = `http://<MI300X_PUBLIC_IP>:8000/v1` — **not** `localhost`.
   - **`ATLASOPS_SKIP_KUBECTL_INJECT=1`** on Space (no kubeconfig).
   - **`ATLASOPS_PUBLIC_BASE_URL`** = `https://lablab-ai-amd-developer-hackathon-atlas-ops.hf.space` (no trailing slash; fix if your slug differs).
   - **`DISCORD_WEBHOOK_URL`** set; rotate if it was ever pasted in chat.
   - **Do not set `ATLASOPS_API_KEY`** on the public demo Space unless the UI is updated to send `X-AtlasOps-Key` — otherwise **`POST /inject` returns 401**.

4. **Smoke test in browser (90 seconds)**  
   Open app → DevTools console:
   - `fetch('/health').then(r=>r.json()).then(console.log)` → `status: ok`, `agent_base` not localhost.  
   - Click **Pod Kill** (or one historical replay) → timeline fills; **Approve** if shown; check Discord.

5. **Judge story (one sentence each)**  
   Real GKE + real metrics; four agents; **human approval** (UI buttons + Discord notice before remediation); MI300X for **SFT + online GRPO**; skip-kubectl only for **fault inject**, agents still use **live tools** elsewhere.

6. **GitHub + slides** — `README` / **`docs/slides.md`** links match the Space you submit; export PDF from Marp if required.

