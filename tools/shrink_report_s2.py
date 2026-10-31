#!/usr/bin/env python3
"""Step S2 EVAL report (docs/shrink_plan_s2.md): reads results/shrink/eval_s2/ (S2) and, through tools/shrink_report.py,
results/shrink/eval/ (S1) and results/shrink/eval_old/ (old shrinker); read-only. Unit: per distinct input (primary)
and per bug (secondary, every bug takes its representative's result). Tokens and floors as in tools/shrink_report.py.
Stage where a capped input's budget ran out (from stage_sizes): no after_tape = tape, after_tape but no after_count =
count, after_count but no after_ddmin = ddmin.
Usage: python3 tools/shrink_report_s2.py   (prints markdown)
"""
import json, statistics
from pathlib import Path
import problems
import shrink_report as R
from aggregate import quant
from run import FOCUS_PROBLEMS

S2 = problems.ROOT / "results/shrink/eval_s2"


def stopped_in(info):
    st = info.get("stage_sizes", {})
    return "tape" if "after_tape" not in st else "count" if "after_count" not in st else "ddmin"


def s2_table(rows, s2):
    print("| problem | shrinker | n | before tokens | before bytes | after tokens | after bytes | after/before (tokens) | after/floor (tokens) | at floor | evaluations median / max | cap / wall hits | success |")
    print("|---|---|---:|---|---|---|---|---|---|---:|---|---|---|")
    for p in FOCUS_PROBLEMS:
        rs = [(r, s2[b]) for b, r in rows if r["problem"] == p]
        ft = R.FLOOR[p][0]
        bt, bb = [x["before"]["tokens"] for _, x in rs], [x["before"]["bytes"] for _, x in rs]
        at, ab = [x["after"]["tokens"] for _, x in rs], [x["after"]["bytes"] for _, x in rs]
        ev = [x["evals"] for _, x in rs]
        print(f"| {p} | S2 | {len(rs)} | {R.mi(bt)} | {R.mi(bb)} | {R.mi(at)} | {R.mi(ab)} | {R.mi([a / b for a, b in zip(at, bt)], '{:.3f}')} "
              f"| {R.mi([a / ft for a in at], '{:.2f}')} | {sum(a == ft for a in at)} ({sum(a == ft for a in at) / len(rs):.1%}) "
              f"| {statistics.median(ev):.0f} / {max(ev)} "
              f"| {sum(x['stop'] == 'evaluation cap' for _, x in rs)} cap, {sum(x['stop'] == 'wall' for _, x in rs)} wall "
              f"| {sum(x['success'] for _, x in rs)} / {len(rs)} |")


def main():
    rep, rows = R.load()  # S1 and old shrinker rows, keyed by distinct-input representative
    s2 = {r["bug"]: json.loads((S2 / r["bug"] / "info.json").read_text()) | {"bug": r["bug"]}
          for r in json.loads((S2 / "summary.json").read_text())["bugs"]}
    assert set(s2) == set(rows), "S2 and S1 cover different distinct inputs"
    distinct = sorted(rows.items())
    per_bug = [(rep[b], rows[rep[b]]) for b in sorted(rep)]
    print(f"Inputs: {len(distinct)} distinct (shrunk once each), {len(per_bug)} bugs.")
    print("\n#### S2, per distinct input (primary)\n")
    s2_table(distinct, s2)
    print("\n#### S2, per bug (secondary; each bug takes its representative's result)\n")
    s2_table(per_bug, s2)
    print("\n#### S1 and old shrinker (repeated unchanged from \"Step S: shrinker evaluation\")")
    R.section(list(rows.values()), "S1 and old, per distinct input (primary)")
    R.section([r for _, r in per_bug], "S1 and old, per bug (secondary)")

    print("\n#### Paired S2 vs S1 on the same distinct inputs (after tokens)\n")
    print("| problem | n | S2 smaller | equal | S2 larger | S2/S1 ratio median [q1, q3] |")
    print("|---|---:|---:|---:|---:|---|")
    for p in FOCUS_PROBLEMS:
        pairs = [(s2[b]["after"]["tokens"], r["new"]["after"]["tokens"]) for b, r in distinct if r["problem"] == p]
        print(f"| {p} | {len(pairs)} | {sum(a < b for a, b in pairs)} | {sum(a == b for a, b in pairs)} | {sum(a > b for a, b in pairs)} "
              f"| {R.mi([a / b for a, b in pairs], '{:.3f}')} |")

    print("\n#### S2 stage-boundary sizes (tokens; medians [q1, q3] over the inputs that reached each boundary)\n")
    print("| problem | start | after tape | after count | after ddmin |")
    print("|---|---|---|---|---|")
    for p in FOCUS_PROBLEMS:
        infos = [s2[b] for b, r in distinct if r["problem"] == p]
        cell = lambda k: (R.mi([i["stage_sizes"][k]["tokens"] for i in infos if k in i["stage_sizes"]]) +
                          f" (n={sum(k in i['stage_sizes'] for i in infos)})")
        print(f"| {p} | {cell('start')} | {cell('after_tape')} | {cell('after_count')} | {cell('after_ddmin')} |")

    print("\n#### S2 header counts before vs after (first input line: n and q; for majority_voting N and Q)\n")
    print("| problem | n | q unchanged | n unchanged | q after/before median [q1, q3] | n after/before median [q1, q3] | after q median | after n median |")
    print("|---|---:|---:|---:|---|---|---:|---:|")
    for p in ("range_linear_add_range_min", "majority_voting"):
        hs = []
        for b, r in distinct:
            if r["problem"] != p:
                continue
            before = Path(s2[b]["bug_dir"], "input.txt").read_text().split("\n")[0].split()
            after = (S2 / b / "input.txt").read_text().split("\n")[0].split()
            hs.append((int(before[0]), int(before[1]), int(after[0]), int(after[1])))
        m = len(hs)
        qr, nr = [h[3] / h[1] for h in hs], [h[2] / h[0] for h in hs]
        print(f"| {p} | {m} | {sum(h[1] == h[3] for h in hs)} ({sum(h[1] == h[3] for h in hs) / m:.1%}) "
              f"| {sum(h[0] == h[2] for h in hs)} ({sum(h[0] == h[2] for h in hs) / m:.1%}) | {R.mi(qr, '{:.3f}')} | {R.mi(nr, '{:.3f}')} "
              f"| {quant([h[3] for h in hs], 50):.0f} | {quant([h[2] for h in hs], 50):.0f} |")

    caps = [(b, s2[b]["problem"], stopped_in(s2[b])) for b, _ in distinct if s2[b]["stop"] == "evaluation cap"]
    walls = [b for b, _ in distinct if s2[b]["stop"] == "wall"]
    fails = [(b, s2[b]["final_verdict"]) for b, _ in distinct if not s2[b]["success"]]
    print(f"\nS2 cap hits ({len(caps)}), with the stage in which the budget ran out:")
    for c in caps:
        print(f"- {c[0]} ({c[1]}): {c[2]}")
    print(f"\nS2 wall-stop hits: {walls or 'none'}")
    print(f"S2 failures (bug, final verdict): {fails or 'none'}")


if __name__ == "__main__":
    main()
