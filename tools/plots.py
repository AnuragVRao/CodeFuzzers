#!/usr/bin/env python3
"""Draws results/charts/*.png (150 dpi) from results/summary.json (only the hunt box plot also reads
per-run values from results/runs.csv). Strategy colours come from tools/style.py.
Charts: scale speed-up / efficiency / predicted-vs-measured per problem, hunt tests-to-bug boxes
at 8 workers, hunt time scaling, pinning, shrinker scaling. Usage: python3 tools/plots.py
"""
import csv, json
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import problems
from style import STRATEGY_COLORS

R = problems.ROOT / "results"
OUT = R / "charts"
COLORS = STRATEGY_COLORS
ORDER = ["random", "noshare", "global", "sharded", "rwlock", "snapshot"]


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)
    print(f"wrote results/charts/{name}")


def scale_charts(rows):
    by_prob = defaultdict(list)
    for r in rows:
        by_prob[r["problem"]].append(r)
    for p, prows in by_prob.items():
        settings = sorted({(r["K"], r["F"]) for r in prows})
        for metric, ylabel, fname in (("speedup_abs", "speed-up vs noshare @1 worker (×)", "scale_speedup"),
                                      ("efficiency_abs", "efficiency (speed-up / workers)", "scale_efficiency")):
            fig, axes = plt.subplots(1, len(settings), figsize=(5 * len(settings), 4), squeeze=False, sharey=True)
            for ax, (k, f) in zip(axes[0], settings):
                for s in ORDER:
                    pts = sorted((r for r in prows if r["strategy"] == s and (r["K"], r["F"]) == (k, f)), key=lambda r: r["workers"])
                    if not pts or pts[0][metric] is None:
                        continue
                    x = [r["workers"] for r in pts]
                    base = [r["tps_median"] / r["speedup_abs"] for r in pts]  # noshare @1 tps
                    div = [b * (w if metric == "efficiency_abs" else 1) for b, w in zip(base, x)]
                    y = [r[metric] for r in pts]
                    lo = [max(0, y_ - r["tps_q1"] / d) for y_, r, d in zip(y, pts, div)]  # IQR (rounding-safe)
                    hi = [max(0, r["tps_q3"] / d - y_) for y_, r, d in zip(y, pts, div)]
                    ax.errorbar(x, y, yerr=[lo, hi], marker="o", capsize=3, color=COLORS[s], label=s)
                xs = sorted({r["workers"] for r in prows})
                ax.plot(xs, xs if metric == "speedup_abs" else [1] * len(xs), "k--", lw=1, label="ideal")
                ax.set_xticks(xs)
                ax.set_title(f"K={k}, F={f}")
                ax.set_xlabel("workers (threads)")
                ax.set_ylabel(ylabel)
                ax.legend(fontsize=8)
            fig.suptitle(f"{p}: {'speed-up' if metric == 'speedup_abs' else 'parallel efficiency'} (scale mode)")
            save(fig, f"{fname}_{p}.png")
        pts = [r for r in prows if (r["K"], r["F"]) == (50, 0.5)]
        if pts:
            fig, ax = plt.subplots(figsize=(6, 4))
            for s in ORDER:
                sp = sorted((r for r in pts if r["strategy"] == s), key=lambda r: r["workers"])
                if not sp:
                    continue
                ax.plot([r["workers"] for r in sp], [r["tps_median"] for r in sp], "-o", color=COLORS[s], label=f"{s} measured")
                pr = [(r["workers"], r["predicted_tps"]) for r in sp if r["predicted_tps"] is not None]
                if pr:
                    ax.plot(*zip(*pr), "--", color=COLORS[s], label=f"{s} predicted")
            ax.set_title(f"{p}: measured vs predicted throughput (K=50, F=0.5)")
            ax.set_xlabel("workers (threads)")
            ax.set_ylabel("tests per second")
            ax.legend(fontsize=7)
            save(fig, f"scale_predicted_{p}.png")


def hunt_box(experiment, hard):
    with open(R / "runs.csv") as fh:
        rows = [r for r in csv.DictReader(fh) if r["experiment"] == experiment and r["workers"] == "8"]
    probs = [p for p in sorted({r["problem"] for r in rows}) if p in hard]
    strats = ["random", "noshare", "rwlock"]
    if not probs:
        return
    fig, ax = plt.subplots(figsize=(max(6, 2.2 * len(probs)), 4.5))
    top = max([float(r["bug_tests_before"]) + 1 for r in rows if r["bug_found"] == "1"] + [1]) * 3
    for i, p in enumerate(probs):
        for j, s in enumerate(strats):
            rs = [r for r in rows if r["problem"] == p and r["strategy"] == s]
            vals = [float(r["bug_tests_before"]) + 1 for r in rs if r["bug_found"] == "1"]  # tests_to_bug
            pos = i * 4 + j
            if vals:
                b = ax.boxplot([vals], positions=[pos], widths=0.7, patch_artist=True)
                b["boxes"][0].set_facecolor(COLORS[s])
            cens = sum(r["bug_found"] != "1" for r in rs)
            if cens:
                ax.plot([pos] * cens, [top] * cens, "x", color=COLORS[s], ms=8)
    for s in strats:
        ax.plot([], [], "s", color=COLORS[s], label=s)
    ax.plot([], [], "kx", label="censored (no bug in time limit)")
    ax.set_yscale("log")
    ax.set_xticks([i * 4 + 1 for i in range(len(probs))], probs, rotation=15, fontsize=8)
    ax.set_title(f"Tests until first bug, 8 workers ({experiment})")
    ax.set_xlabel("problem (hard tier)")
    ax.set_ylabel("tests until first bug (incl. the failing one, log)")
    ax.legend(fontsize=8)
    save(fig, "hunt_tests_to_bug_w8.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s = json.loads((R / "summary.json").read_text())
    bugs = json.loads((problems.DATASET / "bugs.json").read_text())
    scale_charts(s["scale"])
    hunt_box("hunt" if s["meta"]["preset"]["hunt"] == "full" else "hunt-quick", {b["problem"] for b in bugs if b["tier"] == "hard"})

    fig, ax = plt.subplots(figsize=(6, 4))
    for st in ORDER:
        pts = sorted((r for r in s["hunt_time_scaling"] if r["strategy"] == st and r["geomean_time_median"]), key=lambda r: r["workers"])
        if pts:
            ax.plot([r["workers"] for r in pts], [r["geomean_time_median"] for r in pts], "-o", color=COLORS[st], label=st)
    ax.set_title("Time to first bug (geometric mean over hard-tier problems)")
    ax.set_xlabel("workers (threads)")
    ax.set_ylabel("median time to bug (s)")
    ax.legend()
    save(fig, "hunt_time_scaling.png")

    pin = s["pinning"]
    if pin["pinned"]["values"]:
        fig, ax = plt.subplots(figsize=(5, 4))
        for i, (name, c) in enumerate((("pinned", "#2ca02c"), ("unpinned", "#7f7f7f"))):
            ax.bar(i, pin[name]["median"], color=c, alpha=0.6, label=f"{name} (median)")
            ax.plot([i] * len(pin[name]["values"]), pin[name]["values"], "ko", ms=4)
        ax.plot([], [], "ko", ms=4, label="individual runs")
        ax.set_xticks([0, 1], ["pinned", "unpinned"])
        ax.set_title("CPU pinning: global, 8 workers")
        ax.set_xlabel("worker placement")
        ax.set_ylabel("tests per second")
        ax.legend(fontsize=8)
        save(fig, "pinning.png")

    sc = s["shrink"]["scaling"]
    if sc:
        fig, ax = plt.subplots(figsize=(6, 4))
        for p in sorted({r["problem"] for r in sc}):
            pts = sorted((r for r in sc if r["problem"] == p), key=lambda r: r["workers"])
            ax.plot([r["workers"] for r in pts], [r["speedup"] for r in pts], "-o", label=p)
        xs = sorted({r["workers"] for r in sc})
        ax.plot(xs, xs, "k--", lw=1, label="ideal")
        ax.set_title("Shrinker speed-up (process pool)")
        ax.set_xlabel("worker processes")
        ax.set_ylabel("speed-up vs 1 worker (×)")
        ax.legend(fontsize=7)
        save(fig, "shrink_scaling.png")


if __name__ == "__main__":
    main()
