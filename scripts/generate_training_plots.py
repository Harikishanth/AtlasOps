#!/usr/bin/env python3
"""Generate training-evidence PNG charts from committed docs (no re-training needed).

Reads numeric data already present in:
  docs/MI300X_EVIDENCE.md   — SFT loss/token-accuracy log lines
  docs/TRAINING_STORY.md    — GRPO per-step mean reward, benchmark table

Outputs:
  assets/training/sft_loss.png
  assets/training/grpo_reward.png
  assets/training/benchmark_resolution.png
  assets/training/benchmark_per_tier.png

Usage:
  pip install matplotlib   # only dependency
  python scripts/generate_training_plots.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "training"
OUT.mkdir(parents=True, exist_ok=True)

# ── Dark theme matching AtlasOps UI ──────────────────────────────────────────
BG = "#0d1117"
FG = "#c9d1d9"
ACCENT = "#58a6ff"
GREEN = "#57F287"
YELLOW = "#FEE75C"
RED = "#ED4245"
GRID = "#21262d"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "axes.edgecolor": GRID,
    "axes.labelcolor": FG,
    "text.color": FG,
    "xtick.color": FG,
    "ytick.color": FG,
    "grid.color": GRID,
    "grid.alpha": 0.5,
    "font.size": 11,
    "font.family": "sans-serif",
    "savefig.facecolor": BG,
    "savefig.edgecolor": BG,
})


# ── SFT loss + token accuracy ───────────────────────────────────────────────
SFT_DATA = [
    # (epoch, loss, token_accuracy)
    (0.04, 1.2651, 0.7196),
    (0.08, 0.4114, 0.8998),
    (0.12, 0.1950, 0.9483),
    (0.20, 0.1156, 0.9660),
    (0.32, 0.0845, 0.9742),
    (0.55, 0.0557, 0.9821),
    (0.75, 0.0370, 0.9873),
    (0.99, 0.0272, 0.9915),
]

def plot_sft():
    epochs = [d[0] for d in SFT_DATA]
    losses = [d[1] for d in SFT_DATA]
    accs = [d[2] for d in SFT_DATA]

    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Loss", color=RED)
    l1, = ax1.plot(epochs, losses, color=RED, marker="o", markersize=5, linewidth=2, label="Loss")
    ax1.tick_params(axis="y", labelcolor=RED)
    ax1.set_ylim(bottom=0)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Token Accuracy", color=GREEN)
    l2, = ax2.plot(epochs, accs, color=GREEN, marker="s", markersize=5, linewidth=2, label="Token Accuracy")
    ax2.tick_params(axis="y", labelcolor=GREEN)
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1))
    ax2.set_ylim(0.65, 1.0)

    ax1.set_title("SFT on AMD MI300X  ·  2,028 trajectories  ·  254 steps  ·  14 min", fontsize=12, pad=12)
    ax1.legend(handles=[l1, l2], loc="center right", framealpha=0.3)
    ax1.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "sft_loss.png", dpi=150)
    plt.close(fig)
    print(f"  wrote {OUT / 'sft_loss.png'}")


# ── GRPO mean reward per step ────────────────────────────────────────────────
GRPO_REWARDS = [
    0.355, 0.243, 0.073, 0.218, 0.191, 0.147, 0.241, 0.251, 0.070, 0.144,
    0.070, 0.070, 0.048, 0.236, 0.188, 0.011, 0.247, 0.159, 0.158, 0.332,
    0.274, 0.297, 0.021, 0.376, 0.304, 0.352, 0.240, 0.140, 0.222, 0.149,
    0.421, 0.214, 0.140, 0.101, 0.201, 0.341, 0.232, 0.153, 0.219, 0.154,
    0.070, 0.402, 0.000, 0.276, 0.070, 0.261, 0.210, 0.116, 0.214, 0.070,
    0.143, 0.210, 0.319, 0.254, 0.230, 0.205, 0.251, 0.286, 0.182, 0.364,
]

def plot_grpo():
    steps = list(range(1, len(GRPO_REWARDS) + 1))
    # Running best-so-far
    best = []
    cur_best = 0.0
    for r in GRPO_REWARDS:
        cur_best = max(cur_best, r)
        best.append(cur_best)
    # 5-step moving average
    window = 5
    ma = []
    for i in range(len(GRPO_REWARDS)):
        start = max(0, i - window + 1)
        ma.append(sum(GRPO_REWARDS[start:i+1]) / (i - start + 1))

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.bar(steps, GRPO_REWARDS, color=ACCENT, alpha=0.4, width=0.8, label="Per-step mean reward")
    ax.plot(steps, ma, color=YELLOW, linewidth=2, label=f"{window}-step moving avg")
    ax.plot(steps, best, color=GREEN, linewidth=1.5, linestyle="--", alpha=0.7, label="Best so far")
    ax.axhline(y=sum(GRPO_REWARDS)/len(GRPO_REWARDS), color=FG, linewidth=1, linestyle=":", alpha=0.5, label=f"Overall mean ({sum(GRPO_REWARDS)/len(GRPO_REWARDS):.3f})")

    ax.set_xlabel("GRPO Step")
    ax.set_ylabel("Mean Reward")
    ax.set_title("Online GRPO on AMD MI300X  ·  60 steps  ·  4 rollouts  ·  236 episodes  ·  9h 34m", fontsize=12, pad=12)
    ax.legend(loc="upper left", framealpha=0.3, fontsize=9)
    ax.set_ylim(bottom=-0.02)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "grpo_reward.png", dpi=150)
    plt.close(fig)
    print(f"  wrote {OUT / 'grpo_reward.png'}")


# ── Benchmark resolution comparison ─────────────────────────────────────────
def plot_benchmark_resolution():
    models = ["Zero-shot\nBaseline", "AtlasOps\nSFT", "AtlasOps\nGRPO"]
    resolution = [54, 68, 82]
    judge_reward = [0.481, 0.601, 0.729]
    colors = [FG, YELLOW, GREEN]

    fig, ax1 = plt.subplots(figsize=(7, 4.5))
    bars = ax1.bar(models, resolution, color=colors, alpha=0.85, width=0.5, edgecolor=GRID)
    for bar, val in zip(bars, resolution):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5, f"{val}%", ha="center", va="bottom", fontweight="bold", fontsize=13)
    ax1.set_ylabel("Resolution Rate (%)")
    ax1.set_ylim(0, 100)
    ax1.set_title("Incident Resolution Rate  ·  28 chaos scenarios", fontsize=12, pad=12)
    ax1.grid(True, axis="y", alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(models, judge_reward, color=RED, marker="D", markersize=8, linewidth=2, label="Judge reward")
    ax2.set_ylabel("Avg Judge Reward", color=RED)
    ax2.tick_params(axis="y", labelcolor=RED)
    ax2.set_ylim(0.3, 0.85)
    ax2.legend(loc="upper left", framealpha=0.3, fontsize=9)

    fig.tight_layout()
    fig.savefig(OUT / "benchmark_resolution.png", dpi=150)
    plt.close(fig)
    print(f"  wrote {OUT / 'benchmark_resolution.png'}")


# ── Benchmark per-tier ───────────────────────────────────────────────────────
def plot_benchmark_per_tier():
    tiers = ["Single Fault", "Cascade", "Multi-Fault", "Named Replays"]
    baseline = [63, 40, 40, 30]
    grpo     = [88, 78, 76, 72]

    x = range(len(tiers))
    w = 0.35

    fig, ax = plt.subplots(figsize=(8, 4.5))
    b1 = ax.bar([i - w/2 for i in x], baseline, w, label="Zero-shot Baseline", color=FG, alpha=0.7, edgecolor=GRID)
    b2 = ax.bar([i + w/2 for i in x], grpo, w, label="AtlasOps GRPO", color=GREEN, alpha=0.85, edgecolor=GRID)

    for bars in [b1, b2]:
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f"{int(bar.get_height())}%", ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_ylabel("Resolution Rate (%)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(tiers)
    ax.set_ylim(0, 100)
    ax.set_title("Resolution by Scenario Tier  ·  Baseline vs GRPO", fontsize=12, pad=12)
    ax.legend(framealpha=0.3)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "benchmark_per_tier.png", dpi=150)
    plt.close(fig)
    print(f"  wrote {OUT / 'benchmark_per_tier.png'}")


if __name__ == "__main__":
    print("Generating training evidence plots...")
    plot_sft()
    plot_grpo()
    plot_benchmark_resolution()
    plot_benchmark_per_tier()
    print("Done.")
