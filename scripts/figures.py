"""Charts for the README and the evaluation report (reads reports/*.json|csv).

    python scripts/figures.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS, ASSETS = ROOT / "reports", ROOT / "assets"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # validated categorical order
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.axisbelow": True, "legend.frameon": False,
})


def retrieval_chart(m: dict) -> None:
    cfgs = ["dense", "bm25", "hybrid (RRF)", "hybrid + rerank"]
    metrics = [("hit@1", "Hit@1"), ("hit@5", "Hit@5"), ("mrr", "MRR"), ("ndcg@10", "nDCG@10")]
    fig, ax = plt.subplots(figsize=(8.6, 3.9))
    w = 0.19
    for i, cfg in enumerate(cfgs):
        vals = [m["retrieval"][cfg][k] for k, _ in metrics]
        xs = [j + (i - 1.5) * w for j in range(len(metrics))]
        bars = ax.bar(xs, vals, width=w - 0.02, color=SERIES[i], label=cfg, edgecolor=SURFACE, linewidth=1)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.012, f"{v:.2f}", ha="center", va="bottom",
                    fontsize=7.5, color=INK2)
    ax.set_xticks(range(len(metrics)), [lab for _, lab in metrics])
    ax.set_ylim(0.5, 1.06)
    ax.grid(axis="x", visible=False)
    ax.set_title("Retrieval on 119 answerable test questions", loc="left", fontsize=11.5, fontweight="bold")
    ax.legend(ncol=4, loc="upper left", bbox_to_anchor=(0, -0.1), fontsize=9)
    fig.tight_layout()
    fig.savefig(ASSETS / "retrieval_comparison.png", dpi=150)
    plt.close(fig)


def answers_chart(m: dict) -> None:
    bt = m["answers_extractive"]["by_type"]
    order = ["numeric", "table", "factual", "procedural", "cross_doc", "version"]
    labels = [f"{t.replace('_', '-')}\n(n={bt[t]['n']})" for t in order]
    acc = [bt[t]["fact_accuracy"] for t in order]
    neg = [("restricted", bt["restricted"]), ("unanswerable", bt["unanswerable"])]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.2, 3.6), gridspec_kw={"width_ratios": [3, 1.15]})
    bars = a1.bar(range(len(order)), acc, color=SERIES[0], width=0.6, edgecolor=SURFACE)
    for b, v in zip(bars, acc):
        a1.text(b.get_x() + b.get_width() / 2, v + 0.015, f"{v:.0%}", ha="center", fontsize=8.5, color=INK2)
    a1.set_xticks(range(len(order)), labels, fontsize=8.5)
    a1.set_ylim(0, 1.1)
    a1.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    a1.grid(axis="x", visible=False)
    a1.set_title("Key fact in the answer (answerable questions)", loc="left", fontsize=10.5, fontweight="bold")
    vals = [d["abstention_rate"] for _, d in neg]
    bars = a2.bar(range(2), vals, color=SERIES[2], width=0.6, edgecolor=SURFACE)
    for b, v in zip(bars, vals):
        a2.text(b.get_x() + b.get_width() / 2, v + 0.015, f"{v:.0%}", ha="center", fontsize=8.5, color=INK2)
    a2.set_xticks(range(2), [f"{k}\n(n={d['n']})" for k, d in neg], fontsize=8.5)
    a2.set_ylim(0, 1.1)
    a2.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    a2.grid(axis="x", visible=False)
    a2.set_title("Correctly says 'not found'", loc="left", fontsize=10.5, fontweight="bold")
    fig.tight_layout()
    fig.savefig(ASSETS / "answers_by_type.png", dpi=150)
    plt.close(fig)


def calibration_chart(threshold: float) -> None:
    rows = list(csv.DictReader(open(REPORTS / "calibration.csv")))
    t = [float(r["threshold"]) for r in rows]
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    ax.plot(t, [float(r["answer_recall"]) for r in rows], color=SERIES[0], lw=2, label="answerable questions answered")
    ax.plot(t, [float(r["abstain_recall"]) for r in rows], color=SERIES[1], lw=2, label="unanswerable questions refused")
    ax.axvline(threshold, color=INK2, lw=1, ls="--")
    ax.text(threshold + 0.01, 0.05, f"chosen {threshold:.2f}", color=INK2, fontsize=8.5)
    ax.set_xlabel("answerability threshold")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_title("Abstention threshold on the dev set (48 questions)", loc="left", fontsize=11, fontweight="bold")
    ax.legend(loc="lower left", bbox_to_anchor=(0, -0.42), ncol=2, fontsize=9)
    fig.tight_layout()
    fig.savefig(ASSETS / "calibration.png", dpi=150)
    plt.close(fig)


def main() -> None:
    m = json.loads((REPORTS / "metrics.json").read_text())
    retrieval_chart(m)
    answers_chart(m)
    calibration_chart(m["settings"]["min_score"])
    print("figures written to", ASSETS)


if __name__ == "__main__":
    main()
