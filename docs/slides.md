---
marp: true
theme: uncover
paginate: true
backgroundColor: '#060A12'
color: '#E8EDF5'
style: |
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&family=JetBrains+Mono:wght@400;700&display=swap');

  section {
    font-family: 'Inter', sans-serif;
    font-size: 20px;
    background: #060A12;
    color: #E8EDF5;
    padding: 48px 56px;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }

  h1 {
    font-size: 2.8em;
    font-weight: 900;
    letter-spacing: -1px;
    line-height: 1.1;
    margin-bottom: 12px;
  }

  h2 {
    font-size: 1.5em;
    font-weight: 700;
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 20px;
    padding-bottom: 10px;
    border-bottom: 2px solid rgba(255,255,255,0.1);
  }

  h3 {
    font-size: 1.1em;
    font-weight: 600;
    color: #00d4ff;
    letter-spacing: 1px;
    margin-bottom: 8px;
  }

  strong { color: #00D4FF; }
  em { color: #ff4560; font-style: normal; font-weight: 600; }

  code {
    font-family: 'JetBrains Mono', monospace;
    background: rgba(0,212,255,0.08);
    color: #00d4ff;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.85em;
    border: 1px solid rgba(0,212,255,0.2);
  }

  pre {
    background: rgba(0,0,0,0.4);
    border: 1px solid rgba(0,212,255,0.15);
    border-radius: 8px;
    padding: 18px 20px;
    font-size: 0.75em;
  }

  table {
    font-size: 0.8em;
    border-collapse: collapse;
    width: 100%;
    margin-top: 16px;
  }

  th {
    background: rgba(0,212,255,0.1);
    color: #00d4ff;
    padding: 10px 14px;
    text-align: left;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    font-size: 0.8em;
  }

  td {
    padding: 9px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }

  tr:last-child td { border-bottom: none; }

  blockquote {
    border-left: 3px solid #ff4560;
    padding-left: 20px;
    color: #9BA3B8;
    font-style: italic;
    margin: 16px 0;
  }

  section::after {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65em;
    color: rgba(255,255,255,0.2);
    content: attr(data-marpit-pagination) ' / ' attr(data-marpit-pagination-total);
  }

  .accent { color: #00D4FF; }
  .red { color: #FF4560; }
  .green { color: #00E396; }
  .yellow { color: #FFB703; }
  .dim { color: #5A6478; }

---

<!-- _paginate: false -->
<!-- _backgroundColor: #060A12 -->

<div style="text-align:left">

<div style="font-size:0.65em;letter-spacing:4px;color:#FF4560;text-transform:uppercase;margin-bottom:16px;font-weight:700">AMD Developer Hackathon 2026</div>

# AtlasOps

<div style="font-size:1.1em;color:#9BA3B8;font-weight:300;margin-bottom:32px;line-height:1.6">Can 4 AI agents replace<br>an on-call SRE team?</div>

<div style="display:flex;gap:32px;margin-top:24px;flex-wrap:wrap">
<div style="background:rgba(0,212,255,0.06);border:1px solid rgba(0,212,255,0.2);border-radius:8px;padding:10px 16px;font-size:0.7em;color:#00D4FF">Real GKE Cluster · GCP</div>
<div style="background:rgba(255,69,96,0.06);border:1px solid rgba(255,69,96,0.2);border-radius:8px;padding:10px 16px;font-size:0.7em;color:#FF4560">AMD MI300X · 192 GB HBM3</div>
<div style="background:rgba(0,227,150,0.06);border:1px solid rgba(0,227,150,0.2);border-radius:8px;padding:10px 16px;font-size:0.7em;color:#00E396">SFT + Online GRPO Trained</div>
</div>

<div style="margin-top:40px;padding-top:24px;border-top:1px solid rgba(255,255,255,0.08);font-size:0.75em;color:#5A6478">
<strong style="color:#E8EDF5">Harikishanth R</strong> · Reshma Affrin F · Jehrome F &nbsp;|&nbsp; <span style="color:#00D4FF">Da Big Three</span>
</div>

</div>

---

## The Problem

<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-top:8px">

<div style="background:rgba(255,69,96,0.05);border:1px solid rgba(255,69,96,0.2);border-radius:10px;padding:22px">
<div style="font-size:2.4em;font-weight:900;color:#FF4560">2:47 AM</div>
<div style="font-size:0.75em;color:#9BA3B8;margin-top:8px;line-height:1.6">When P1 alerts fire on average. Your on-call engineer is asleep — or stressed, rushing.</div>
</div>

<div style="background:rgba(255,183,3,0.05);border:1px solid rgba(255,183,3,0.2);border-radius:10px;padding:22px">
<div style="font-size:2.4em;font-weight:900;color:#FFB703">~25 min</div>
<div style="font-size:0.75em;color:#9BA3B8;margin-top:8px;line-height:1.6">Average human MTTR for a cascade incident. Revenue bleeding the entire time.</div>
</div>

<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.2);border-radius:10px;padding:22px">
<div style="font-size:2.4em;font-weight:900;color:#00D4FF">$250B</div>
<div style="font-size:0.75em;color:#9BA3B8;margin-top:8px;line-height:1.6">Global observability + SRE market. On-call burnout is the industry's most expensive unsolved problem.</div>
</div>

</div>

<div style="margin-top:20px;background:rgba(255,69,96,0.04);border-left:3px solid #FF4560;padding:14px 20px;border-radius:0 6px 6px 0;font-size:0.8em;color:#9BA3B8">
Every SRE team has a war story. The 3 AM page. The cascading failure nobody understood for 40 minutes. The postmortem that blamed "human error." <strong style="color:#E8EDF5">The real failure was that there was no system to help them think faster.</strong>
</div>

---

## Introducing AtlasOps

<div style="font-size:0.9em;color:#9BA3B8;margin-bottom:24px">Four specialized AI agents. One AMD MI300X. One real GKE cluster. No simulations.</div>

<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">

<div style="text-align:center;background:rgba(255,69,96,0.05);border:1px solid rgba(255,69,96,0.25);border-radius:10px;padding:18px 10px">
<div style="font-size:1.8em;margin-bottom:10px">🔴</div>
<div style="font-weight:700;color:#FF4560;font-size:0.85em;letter-spacing:1px;margin-bottom:8px">TRIAGE</div>
<div style="font-size:0.7em;color:#9BA3B8;line-height:1.7">Ack alert<br>Classify severity<br>Map blast radius<br><4 tool calls</div>
</div>

<div style="text-align:center;background:rgba(123,97,255,0.05);border:1px solid rgba(123,97,255,0.25);border-radius:10px;padding:18px 10px">
<div style="font-size:1.8em;margin-bottom:10px">🔍</div>
<div style="font-weight:700;color:#7B61FF;font-size:0.85em;letter-spacing:1px;margin-bottom:8px">DIAGNOSIS</div>
<div style="font-size:0.7em;color:#9BA3B8;line-height:1.7">PromQL queries<br>Jaeger traces<br>kubectl logs<br>Root cause ID</div>
</div>

<div style="text-align:center;background:rgba(255,183,3,0.05);border:1px solid rgba(255,183,3,0.25);border-radius:10px;padding:18px 10px">
<div style="font-size:1.8em;margin-bottom:10px">🔧</div>
<div style="font-weight:700;color:#FFB703;font-size:0.85em;letter-spacing:1px;margin-bottom:8px">REMEDIATION</div>
<div style="font-size:0.7em;color:#9BA3B8;line-height:1.7">Argo CD rollback<br>kubectl scale<br>Alert silence<br>Verify fix</div>
</div>

<div style="text-align:center;background:rgba(0,227,150,0.05);border:1px solid rgba(0,227,150,0.25);border-radius:10px;padding:18px 10px">
<div style="font-size:1.8em;margin-bottom:10px">📣</div>
<div style="font-weight:700;color:#00E396;font-size:0.85em;letter-spacing:1px;margin-bottom:8px">COMMS</div>
<div style="font-size:0.7em;color:#9BA3B8;line-height:1.7">Slack update<br>Postmortem<br>Status page<br>Action items</div>
</div>

</div>

<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:12px 20px;font-family:'JetBrains Mono',monospace;font-size:0.7em;color:#5A6478;text-align:center">
Alert → <span style="color:#FF4560">Triage</span> → <span style="color:#7B61FF">Diagnosis</span> → [<span style="color:#FFB703">Approval Gate</span>] → <span style="color:#FFB703">Remediation</span> → <span style="color:#00E396">Comms</span> → Postmortem
</div>

---

## Real Infrastructure — Not a Simulation

<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:4px">

<div>
<h3>☁ Google Cloud Platform</h3>
<div style="display:flex;flex-direction:column;gap:8px;font-size:0.78em">
<div style="display:flex;align-items:baseline;gap:10px"><span style="color:#00E396;font-weight:700">▸</span><span><strong style="color:#E8EDF5">GKE Standard Cluster</strong> — us-central1, 3× e2-standard-4</span></div>
<div style="display:flex;align-items:baseline;gap:10px"><span style="color:#00E396;font-weight:700">▸</span><span><strong style="color:#E8EDF5">Online Boutique</strong> — 11 real microservices (Go, Python, Node, Java, C#, gRPC)</span></div>
<div style="display:flex;align-items:baseline;gap:10px"><span style="color:#00E396;font-weight:700">▸</span><span><strong style="color:#E8EDF5">Chaos Mesh</strong> — PodChaos · NetworkChaos · StressChaos · DNSChaos · IOChaos · TimeChaos</span></div>
<div style="display:flex;align-items:baseline;gap:10px"><span style="color:#00E396;font-weight:700">▸</span><span><strong style="color:#E8EDF5">Prometheus + Grafana + Jaeger + OTel</strong> — full observability stack</span></div>
<div style="display:flex;align-items:baseline;gap:10px"><span style="color:#00E396;font-weight:700">▸</span><span><strong style="color:#E8EDF5">Argo CD</strong> — GitOps rollbacks, real execution</span></div>
<div style="display:flex;align-items:baseline;gap:10px"><span style="color:#00E396;font-weight:700">▸</span><span><strong style="color:#E8EDF5">Cloud SQL</strong> (Postgres 15) + Cloud PubSub + Cloud Monitoring</span></div>
<div style="display:flex;align-items:baseline;gap:10px"><span style="color:#00E396;font-weight:700">▸</span><span><strong style="color:#E8EDF5">Alertmanager</strong> — webhook fires agents on real alerts</span></div>
</div>
</div>

<div>
<h3>🛠 20 Real SRE Tools</h3>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:0.7em">
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:7px 10px;color:#00D4FF">kubectl (7 cmds)</div>
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:7px 10px;color:#00D4FF">promql_query</div>
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:7px 10px;color:#00D4FF">promql_range</div>
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:7px 10px;color:#00D4FF">jaeger_search</div>
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:7px 10px;color:#00D4FF">jaeger_get_trace</div>
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:7px 10px;color:#00D4FF">argocd_rollback</div>
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:7px 10px;color:#00D4FF">gcloud_logs_read</div>
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:7px 10px;color:#00D4FF">cloud_monitoring</div>
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:7px 10px;color:#00D4FF">alertmanager_silence</div>
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:7px 10px;color:#00D4FF">postmortem_draft</div>
</div>
<div style="margin-top:12px;font-size:0.7em;color:#5A6478;font-style:italic">Every tool hits a real API. No mocks in production.</div>
</div>

</div>

---

## 38 Chaos Scenarios + Infinite Adversarial Generation

<div style="display:grid;grid-template-columns:1fr 1.2fr;gap:24px;margin-top:8px">

<div>
<table>
<thead><tr><th>Tier</th><th>Count</th><th>Difficulty</th></tr></thead>
<tbody>
<tr><td>Single-fault</td><td><strong>8</strong></td><td style="color:#00E396">Beginner</td></tr>
<tr><td>Cascade</td><td><strong>5</strong></td><td style="color:#FFB703">Hard</td></tr>
<tr><td>Multi-fault</td><td><strong>5</strong></td><td style="color:#FF4560">Expert</td></tr>
<tr><td>Named Replays</td><td><strong>10</strong></td><td style="color:#FF4560">Expert</td></tr>
<tr><td style="color:#00D4FF">Dynamic Adversarial</td><td style="color:#00D4FF"><strong>∞</strong></td><td style="color:#00D4FF">72B-designed</td></tr>
</tbody>
</table>
</div>

<div>
<h3>10 Named Historical Replays</h3>
<div style="display:flex;flex-direction:column;gap:7px;font-size:0.75em">
<div><span style="color:#FFB703">⚡</span> <strong>Cloudflare 2019</strong> — Regex CPU storm, 85% traffic down</div>
<div><span style="color:#FFB703">⚡</span> <strong>GitHub 2018</strong> — DB failover loop, 24h incident</div>
<div><span style="color:#FFB703">⚡</span> <strong>AWS S3 2017</strong> — Typo'd command cascaded globally</div>
<div><span style="color:#FFB703">⚡</span> <strong>Discord 2022</strong> — Redis thundering herd</div>
<div><span style="color:#FFB703">⚡</span> <strong>Fastly 2021</strong> — Bad VCL config, internet outage</div>
<div><span style="color:#FFB703">⚡</span> <strong>Facebook BGP 2021</strong> — Control plane partition</div>
<div><span style="color:#FFB703">⚡</span> <strong>Knight Capital 2012</strong> — Partial deploy, $440M loss</div>
<div style="color:#5A6478">+ Datadog 2023 · Slack 2022 · Azure DNS 2019</div>
</div>
</div>

</div>

<div style="margin-top:16px;background:rgba(0,212,255,0.04);border:1px solid rgba(0,212,255,0.15);border-radius:8px;padding:12px 18px;font-size:0.75em;color:#9BA3B8">
<strong style="color:#00D4FF">Adversarial designer:</strong> After each benchmark run, the Qwen2.5-72B judge analyzes the agent's failure modes and generates brand-new Chaos Mesh YAML targeting those exact weaknesses. The test set gets harder as the model improves — impossible to memorize.
</div>

---

## Why AMD MI300X Was Non-Negotiable

<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:8px">

<div>
<h3>Memory Requirements</h3>
<div style="background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:16px;font-family:'JetBrains Mono',monospace;font-size:0.7em;line-height:2">
<div style="color:#9BA3B8">Qwen2.5-7B base (shared)  <span style="color:#00D4FF;float:right">~4 GB</span></div>
<div style="color:#9BA3B8">4× LoRA adapters (r=16)   <span style="color:#00D4FF;float:right">~160 MB</span></div>
<div style="color:#9BA3B8">Qwen2.5-72B judge (AWQ)   <span style="color:#FFB703;float:right">~37 GB</span></div>
<div style="color:#9BA3B8">GRPO training buffers     <span style="color:#FFB703;float:right">~12 GB</span></div>
<div style="color:#9BA3B8">vLLM KV cache             <span style="color:#FFB703;float:right">~70 GB</span></div>
<div style="border-top:1px solid rgba(255,255,255,0.1);margin-top:8px;padding-top:8px;color:#E8EDF5;font-weight:700">Total required <span style="color:#00E396;float:right">~126 GB</span></div>
</div>
</div>

<div>
<h3>GPU Comparison</h3>
<div style="display:flex;flex-direction:column;gap:10px;margin-top:8px">
<div style="background:rgba(255,69,96,0.05);border:1px solid rgba(255,69,96,0.2);border-radius:8px;padding:14px 16px;font-size:0.8em">
<div style="color:#FF4560;font-weight:700;margin-bottom:4px">A100 (80 GB) ❌</div>
<div style="color:#9BA3B8">Fits agents OR judge — not both simultaneously. Online GRPO impossible.</div>
</div>
<div style="background:rgba(255,69,96,0.05);border:1px solid rgba(255,69,96,0.2);border-radius:8px;padding:14px 16px;font-size:0.8em">
<div style="color:#FF4560;font-weight:700;margin-bottom:4px">T4 (16 GB) ❌</div>
<div style="color:#9BA3B8">Can't fit Qwen2.5-7B at all. CUDA OOM at model load.</div>
</div>
<div style="background:rgba(0,227,150,0.05);border:1px solid rgba(0,227,150,0.3);border-radius:8px;padding:14px 16px;font-size:0.8em">
<div style="color:#00E396;font-weight:700;margin-bottom:4px">MI300X 192 GB HBM3 ✅</div>
<div style="color:#9BA3B8">All 5 models co-hosted. 66 GB free. 18× faster inference vs shared API.</div>
</div>
</div>
</div>

</div>

---

## Training Pipeline — SFT → Online GRPO

<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:4px">

<div>
<h3>Phase 1: Supervised Fine-Tuning</h3>
<div style="font-size:0.78em;color:#9BA3B8;margin-bottom:10px">2,028 real GKE trajectories · QLoRA 4-bit NF4 · LoRA r=16</div>
<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.07);border-radius:8px;padding:14px;font-family:'JetBrains Mono',monospace;font-size:0.65em;line-height:1.9">
<div><span style="color:#5A6478">loss:</span> <span style="color:#FF4560">1.265</span> → <span style="color:#5A6478">0.48</span> → <span style="color:#5A6478">0.19</span> → <span style="color:#00E396">0.027</span></div>
<div><span style="color:#5A6478">accuracy:</span> <span style="color:#FF4560">71.96%</span> → <span style="color:#00E396">99.10%</span></div>
<div><span style="color:#5A6478">time:</span> <span style="color:#00D4FF">14 min 16 sec</span></div>
<div><span style="color:#5A6478">adapter:</span> <span style="color:#00D4FF">78 MB LoRA</span></div>
</div>
<div style="margin-top:10px;font-size:0.72em;color:#5A6478">Model learned: correct tool-call sequence, promql before argocd rollback, postmortem structure</div>
</div>

<div>
<h3>Phase 2: Online GRPO</h3>
<div style="font-size:0.78em;color:#9BA3B8;margin-bottom:10px">60 steps · 236 real GKE rollout episodes · DAPO loss</div>
<div style="background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.07);border-radius:8px;padding:14px;font-family:'JetBrains Mono',monospace;font-size:0.65em;line-height:1.9">
<div><span style="color:#5A6478">step 01:</span> mean=<span style="color:#FF4560">0.355</span>  max=0.539</div>
<div><span style="color:#5A6478">step 24:</span> mean=<span style="color:#FFB703">0.376</span>  max=0.700</div>
<div><span style="color:#5A6478">step 31:</span> mean=<span style="color:#00E396">0.421</span>  max=0.671 ← peak</div>
<div><span style="color:#5A6478">step 60:</span> mean=<span style="color:#00E396">0.364</span>  max=0.506</div>
<div><span style="color:#5A6478">overall:</span> mean=<span style="color:#00D4FF">0.200</span>  runtime=<span style="color:#00D4FF">9h 34m</span></div>
</div>
<div style="margin-top:10px;font-size:0.72em;color:#5A6478">True online RL: every step = real chaos + real rollouts + real cluster scoring</div>
</div>

</div>

---

## What Makes Our Training Unique

| Feature | Standard GRPO | **AtlasOps** |
|---|---|---|
| Environment | Simulator / offline | **Real GKE cluster, live kubectl** |
| Loss function | GRPO | **DAPO** — stable on sparse rewards |
| Reward signal | Episode-level only | **Dense per-step** + episode contract |
| Curriculum | Random / fixed | **Spaced repetition** — mastery tracking |
| Scenario generation | Static | **∞ adversarial** — 72B judge writes new Chaos YAML |
| Judge | Single rubric | **3 personas** — Junior / Senior / Principal |

<div style="margin-top:20px;display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px">
<div style="background:rgba(255,69,96,0.05);border:1px solid rgba(255,69,96,0.2);border-radius:8px;padding:12px;text-align:center;font-size:0.75em">
<div style="font-size:1.5em;font-weight:900;color:#FF4560">−0.25</div>
<div style="color:#9BA3B8;margin-top:4px">false resolution penalty</div>
</div>
<div style="background:rgba(255,69,96,0.05);border:1px solid rgba(255,69,96,0.2);border-radius:8px;padding:12px;text-align:center;font-size:0.75em">
<div style="font-size:1.5em;font-weight:900;color:#FF4560">−0.20</div>
<div style="color:#9BA3B8;margin-top:4px">hallucinated evidence</div>
</div>
<div style="background:rgba(0,227,150,0.05);border:1px solid rgba(0,227,150,0.2);border-radius:8px;padding:12px;text-align:center;font-size:0.75em">
<div style="font-size:1.5em;font-weight:900;color:#00E396">+0.15</div>
<div style="color:#9BA3B8;margin-top:4px">red herring bonus</div>
</div>
<div style="background:rgba(0,227,150,0.05);border:1px solid rgba(0,227,150,0.2);border-radius:8px;padding:12px;text-align:center;font-size:0.75em">
<div style="font-size:1.5em;font-weight:900;color:#00E396">+0.08</div>
<div style="color:#9BA3B8;margin-top:4px">mutating action success</div>
</div>
</div>

---

## Benchmark Results

<div style="font-size:0.8em;color:#9BA3B8;margin-bottom:16px">28 frozen scenarios · Real GKE cluster · AMD MI300X · Qwen2.5-7B</div>

<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px">
<div style="background:rgba(0,227,150,0.05);border:1px solid rgba(0,227,150,0.3);border-radius:10px;padding:18px;text-align:center">
<div style="font-size:2.5em;font-weight:900;color:#00E396">82%</div>
<div style="font-size:0.7em;color:#9BA3B8;margin-top:6px;text-transform:uppercase;letter-spacing:1px">Resolution Rate</div>
<div style="font-size:0.75em;color:#00E396;margin-top:4px">+28pp vs zero-shot</div>
</div>
<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.3);border-radius:10px;padding:18px;text-align:center">
<div style="font-size:2.5em;font-weight:900;color:#00D4FF">0.729</div>
<div style="font-size:0.7em;color:#9BA3B8;margin-top:6px;text-transform:uppercase;letter-spacing:1px">Avg Reward</div>
<div style="font-size:0.75em;color:#00D4FF;margin-top:4px">72B judge-scored</div>
</div>
<div style="background:rgba(255,183,3,0.05);border:1px solid rgba(255,183,3,0.3);border-radius:10px;padding:18px;text-align:center">
<div style="font-size:2.5em;font-weight:900;color:#FFB703">59s</div>
<div style="font-size:0.7em;color:#9BA3B8;margin-top:6px;text-transform:uppercase;letter-spacing:1px">Avg MTTR</div>
<div style="font-size:0.75em;color:#FFB703;margin-top:4px">vs ~25 min human</div>
</div>
<div style="background:rgba(255,69,96,0.05);border:1px solid rgba(255,69,96,0.3);border-radius:10px;padding:18px;text-align:center">
<div style="font-size:2.5em;font-weight:900;color:#FF4560">78%</div>
<div style="font-size:0.7em;color:#9BA3B8;margin-top:6px;text-transform:uppercase;letter-spacing:1px">Cascade Rate</div>
<div style="font-size:0.75em;color:#FF4560;margin-top:4px">+38pp vs zero-shot</div>
</div>
</div>

| Model | Resolution | Reward | Cascade | Named Replays | Unsafe Actions |
|---|---|---|---|---|---|
| Qwen2.5-7B zero-shot | 54% | 0.481 | 40% | 30% | 5 |
| AtlasOps SFT | 68% | 0.601 | 62% | 55% | 3 |
| **AtlasOps GRPO (MI300X)** | **82%** | **0.729** | **78%** | **72%** | **1** |

---

## Production Safety — No Agent Can Cause an Outage

<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:8px">

<div style="background:rgba(255,69,96,0.04);border:1px solid rgba(255,69,96,0.2);border-radius:10px;padding:20px">
<div style="font-size:1.4em;margin-bottom:10px">🚦</div>
<div style="font-weight:700;color:#FF4560;margin-bottom:8px;letter-spacing:1px">APPROVAL GATE</div>
<div style="font-size:0.78em;color:#9BA3B8;line-height:1.8">
<strong style="color:#E8EDF5">P0:</strong> Human required — no auto-execution<br>
<strong style="color:#E8EDF5">P1:</strong> Approval window (default <strong>300s</strong>; set <code>APPROVAL_TIMEOUT_SECONDS</code>) + UI Approve/Reject<br>
<strong style="color:#E8EDF5">P2/P3:</strong> Fully automatic<br>
Token-based callbacks via REST API
</div>
</div>

<div style="background:rgba(255,183,3,0.04);border:1px solid rgba(255,183,3,0.2);border-radius:10px;padding:20px">
<div style="font-size:1.4em;margin-bottom:10px">⚡</div>
<div style="font-weight:700;color:#FFB703;margin-bottom:8px;letter-spacing:1px">CIRCUIT BREAKER</div>
<div style="font-size:0.78em;color:#9BA3B8;line-height:1.8">
50 tool calls per incident max<br>
10 mutating actions per hour<br>
3 consecutive failures → OPEN state<br>
Tripped 1× during GRPO training (working as designed)
</div>
</div>

<div style="background:rgba(0,212,255,0.04);border:1px solid rgba(0,212,255,0.2);border-radius:10px;padding:20px">
<div style="font-size:1.4em;margin-bottom:10px">🔗</div>
<div style="font-weight:700;color:#00D4FF;margin-bottom:8px;letter-spacing:1px">INCIDENT CORRELATOR</div>
<div style="font-size:0.78em;color:#9BA3B8;line-height:1.8">
5-minute deduplication window<br>
Fingerprint-based alert grouping<br>
Prevents 10 parallel chains on one cascade<br>
Tracks all active incidents
</div>
</div>

<div style="background:rgba(0,227,150,0.04);border:1px solid rgba(0,227,150,0.2);border-radius:10px;padding:20px">
<div style="font-size:1.4em;margin-bottom:10px">📋</div>
<div style="font-weight:700;color:#00E396;margin-bottom:8px;letter-spacing:1px">HMAC AUDIT LOG</div>
<div style="font-size:0.78em;color:#9BA3B8;line-height:1.8">
Hash-chained entries — tamper-evident<br>
Every tool call + approval logged<br>
`verify_integrity()` checks full chain<br>
Cryptographic proof of what happened
</div>
</div>

</div>

---

## Cloudflare 2019 — Replay Postmortem

<div style="font-size:0.78em;color:#9BA3B8;margin-bottom:14px">What happened when we ran AtlasOps against a real recreation of the incident that took down 85% of Cloudflare's traffic</div>

<div style="background:rgba(0,0,0,0.35);border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:18px 20px;font-size:0.73em;line-height:2">
<div><span style="color:#5A6478;font-family:'JetBrains Mono'">00:03</span> &nbsp;<span style="color:#FF4560;font-weight:700">TRIAGE</span> &nbsp; PagerDuty ACK · severity P1 · blast: frontend + checkout + cart</div>
<div><span style="color:#5A6478;font-family:'JetBrains Mono'">00:08</span> &nbsp;<span style="color:#7B61FF;font-weight:700">DIAGNOSIS</span> &nbsp; promql → 5xx surge on checkoutservice (error_rate: 34%)</div>
<div><span style="color:#5A6478;font-family:'JetBrains Mono'">00:10</span> &nbsp;<span style="color:#7B61FF;font-weight:700">DIAGNOSIS</span> &nbsp; jaeger → timeout chain ends at currencyservice (CPU at 1999m/2000m)</div>
<div><span style="color:#5A6478;font-family:'JetBrains Mono'">00:13</span> &nbsp;<span style="color:#FFB703;font-weight:700">REMEDIATION</span> &nbsp; argocd rollback currencyservice → revision 3 ✓</div>
<div><span style="color:#5A6478;font-family:'JetBrains Mono'">00:18</span> &nbsp;<span style="color:#FFB703;font-weight:700">REMEDIATION</span> &nbsp; promql confirms error_rate &lt; 0.1% · RESOLVED</div>
<div><span style="color:#5A6478;font-family:'JetBrains Mono'">00:22</span> &nbsp;<span style="color:#00E396;font-weight:700">COMMS</span> &nbsp; slack posted · statuspage updated</div>
<div><span style="color:#5A6478;font-family:'JetBrains Mono'">00:24</span> &nbsp;<span style="color:#00E396;font-weight:700">COMMS</span> &nbsp; postmortem saved → docs/postmortems/cloudflare-2019-replay.md</div>
</div>

<div style="margin-top:14px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px">
<div style="text-align:center;background:rgba(0,227,150,0.05);border:1px solid rgba(0,227,150,0.2);border-radius:8px;padding:12px">
<div style="font-size:1.8em;font-weight:900;color:#00E396">4m 12s</div>
<div style="font-size:0.7em;color:#9BA3B8;margin-top:4px">Total MTTR</div>
</div>
<div style="text-align:center;background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.2);border-radius:8px;padding:12px">
<div style="font-size:1.8em;font-weight:900;color:#00D4FF">3</div>
<div style="font-size:0.7em;color:#9BA3B8;margin-top:4px">Tool calls to root cause</div>
</div>
<div style="text-align:center;background:rgba(255,183,3,0.05);border:1px solid rgba(255,183,3,0.2);border-radius:8px;padding:12px">
<div style="font-size:1.8em;font-weight:900;color:#FFB703">0.856</div>
<div style="font-size:0.7em;color:#9BA3B8;margin-top:4px">Judge score</div>
</div>
</div>

---

## Tech Stack

<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:8px">

<div style="background:rgba(11,17,32,0.8);border:1px solid var(--border,rgba(255,255,255,0.08));border-radius:10px;padding:18px">
<h3 style="color:#FF4560">AMD Hardware</h3>
<div style="font-size:0.78em;display:flex;flex-direction:column;gap:8px;color:#9BA3B8">
<div>MI300X — 192 GB HBM3</div>
<div>ROCm 7.2</div>
<div>vLLM 0.17.1 (ROCm build)</div>
<div>18× speedup vs shared API</div>
<div>312ms p50 inference latency</div>
<div>5 models co-hosted simultaneously</div>
</div>
</div>

<div style="background:rgba(11,17,32,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:18px">
<h3 style="color:#7B61FF">ML Training</h3>
<div style="font-size:0.78em;display:flex;flex-direction:column;gap:8px;color:#9BA3B8">
<div>Qwen2.5-7B-Instruct × 4</div>
<div>Qwen2.5-72B-Instruct-AWQ (judge)</div>
<div>TRL 1.4.0 — SFTTrainer + GRPOTrainer</div>
<div>PEFT QLoRA — 4-bit NF4, r=16</div>
<div>BitsAndBytes-ROCm</div>
<div>HF Optimum-AMD (inference)</div>
</div>
</div>

<div style="background:rgba(11,17,32,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:18px">
<h3 style="color:#00E396">Application</h3>
<div style="font-size:0.78em;display:flex;flex-direction:column;gap:8px;color:#9BA3B8">
<div>FastAPI + custom SSE streaming</div>
<div>Chaos Mesh (6 fault types)</div>
<div>Prometheus + Grafana + Jaeger</div>
<div>Argo CD GitOps</div>
<div>GKE Standard · Cloud SQL</div>
<div>Docker · HuggingFace Spaces</div>
</div>
</div>

</div>

---

<!-- _paginate: false -->
<!-- _backgroundColor: #060A12 -->

<div style="text-align:center">

<div style="font-size:0.65em;letter-spacing:4px;color:#5A6478;text-transform:uppercase;margin-bottom:20px">AMD Developer Hackathon 2026</div>

<h1 style="font-size:3em;color:#00D4FF;text-shadow:0 0 40px rgba(0,212,255,0.4);margin-bottom:16px">AtlasOps</h1>

<div style="font-size:1em;color:#9BA3B8;margin-bottom:32px;line-height:1.8">
Real GKE cluster · Real training · Real results<br>
<strong style="color:#E8EDF5">54% → 82% resolution rate. Zero simulations.</strong>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;max-width:600px;margin:0 auto 32px">
<div style="background:rgba(0,227,150,0.06);border:1px solid rgba(0,227,150,0.2);border-radius:8px;padding:12px;font-size:0.75em">
<div style="color:#00E396;font-weight:700">GitHub</div>
<div style="color:#5A6478;margin-top:4px;font-size:0.9em">Harikishanth/AtlasOps</div>
</div>
<div style="background:rgba(0,212,255,0.06);border:1px solid rgba(0,212,255,0.2);border-radius:8px;padding:12px;font-size:0.75em">
<div style="color:#00D4FF;font-weight:700">HF Space</div>
<div style="color:#5A6478;margin-top:4px;font-size:0.9em;line-height:1.35">lablab-ai-amd-developer-hackathon / <strong style="color:#E8EDF5">atlas-ops</strong></div>
<div style="color:#5A6478;margin-top:6px;font-size:0.75em;line-height:1.4"><span style="font-family:'JetBrains Mono',monospace">lablab-ai-amd-developer-hackathon-atlas-ops.hf.space</span></div>
</div>
<div style="background:rgba(255,183,3,0.06);border:1px solid rgba(255,183,3,0.2);border-radius:8px;padding:12px;font-size:0.75em">
<div style="color:#FFB703;font-weight:700">Team</div>
<div style="color:#5A6478;margin-top:4px;font-size:0.9em">Da Big Three</div>
</div>
</div>

<div style="font-size:0.8em;color:#5A6478;padding-top:24px;border-top:1px solid rgba(255,255,255,0.06)">
<strong style="color:#9BA3B8">Harikishanth R</strong> &nbsp;·&nbsp; Reshma Affrin F &nbsp;·&nbsp; Jehrome F
</div>

</div>
