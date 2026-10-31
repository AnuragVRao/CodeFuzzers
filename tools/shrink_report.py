#!/usr/bin/env python3
"""Step S EVAL report (docs/shrink_plan.md): reads results/shrink/eval/ (new shrinker) and results/shrink/eval_old/
(old shrinker); read-only. Unit: per distinct input (primary; one representative per distinct input) and per bug
(secondary; every bug takes its representative's result, results/shrink/eval/representatives.json).
"After" for the old shrinker = its shrunk/input.txt; its success is re-judged with the same predicate (tools/shrink.py
Judge, fresh processes). Tokens as in tools/shrink.py (-?\\d+|\\S). "At the floor" = after tokens == floor tokens.
Usage: python3 tools/shrink_report.py   (prints markdown)
"""
import json, os, shutil, statistics
from pathlib import Path
import problems, shrink
from aggregate import quant
from run import FOCUS_PROBLEMS

ROOT = problems.ROOT
NEW, OLD = ROOT / "results/shrink/eval", ROOT / "results/shrink/eval_old"
FLOOR = {"majority_voting": (69, 140), "range_linear_add_range_min": (11, 30), "longest_common_substring": (3, 5)}


def mi(v, fmt="{:.0f}"):
    return f"{fmt.format(quant(v, 50))} [{fmt.format(quant(v, 25))}, {fmt.format(quant(v, 75))}]" if v else "-"


def load():
    rep = json.loads((NEW / "representatives.json").read_text())
    new = {r["bug"]: r for r in json.loads((NEW / "summary.json").read_text())["bugs"]}
    old = {r["bug"]: r for r in json.loads((OLD / "summary.json").read_text())["bugs"]}
    tmp = Path(f"/dev/shm/cf_shrink_report_{os.getpid()}")
    tmp.mkdir(exist_ok=True)
    rows = {}
    for bid, n in new.items():
        p = n["problem"]
        o = old[bid]
        text = (OLD / bid / "bug" / "shrunk" / "input.txt").read_text() if (OLD / bid / "bug" / "shrunk" / "input.txt").exists() else None
        before = (OLD / bid / "bug" / "input.txt").read_text()
        rows[bid] = dict(problem=p, population=n["population"], new=n,
                         old=dict(after_tokens=shrink.ntokens(text) if text else None, after_bytes=len(text.encode()) if text else None,
                                  before_tokens=shrink.ntokens(before), before_bytes=len(before.encode()), tests=o["tests_used"],
                                  exit=o["exit"], verdict=shrink.Judge(p, tmp).verdict(text) if text else "no output"))
    shutil.rmtree(tmp, ignore_errors=True)
    return rep, rows


def section(rows, title):
    print(f"\n#### {title}\n")
    print("| problem | shrinker | n | before tokens | before bytes | after tokens | after bytes | after/before (tokens) | after/floor (tokens) | at floor | evaluations median / max | cap / budget hits | success |")
    print("|---|---|---:|---|---|---|---|---|---|---:|---|---|---|")
    for p in FOCUS_PROBLEMS:
        rs = [r for r in rows if r["problem"] == p]
        ft = FLOOR[p][0]
        for who in ("new", "old"):
            if who == "new":
                bt, bb = [r["new"]["before"]["tokens"] for r in rs], [r["new"]["before"]["bytes"] for r in rs]
                at, ab = [r["new"]["after"]["tokens"] for r in rs], [r["new"]["after"]["bytes"] for r in rs]
                ev = [r["new"]["evals"] for r in rs]
                hits = f"{sum(r['new']['stop'] == 'evaluation cap' for r in rs)} cap, {sum(r['new']['stop'] == 'wall' for r in rs)} wall"
                succ = sum(r["new"]["success"] for r in rs)
            else:
                bt, bb = [r["old"]["before_tokens"] for r in rs], [r["old"]["before_bytes"] for r in rs]
                at, ab = [r["old"]["after_tokens"] for r in rs], [r["old"]["after_bytes"] for r in rs]
                ev = [r["old"]["tests"] for r in rs]
                hits = f"{sum(t >= 4000 for t in ev)} at 4,000 tests"
                succ = sum(r["old"]["verdict"] == "WA" for r in rs)
            print(f"| {p} | {who} | {len(rs)} | {mi(bt)} | {mi(bb)} | {mi(at)} | {mi(ab)} | {mi([a / b for a, b in zip(at, bt)], '{:.3f}')} "
                  f"| {mi([a / ft for a in at], '{:.2f}')} | {sum(a == ft for a in at)} ({sum(a == ft for a in at) / len(rs):.1%}) "
                  f"| {statistics.median(ev):.0f} / {max(ev)} | {hits} | {succ} / {len(rs)} |")


def main():
    rep, rows = load()
    distinct = [rows[b] for b in rows]
    per_bug = [rows[rep[b]] for b in rep]
    print(f"Inputs: {len(distinct)} distinct (shrunk once each), {len(per_bug)} bugs.")
    section(distinct, "Per distinct input (primary)")
    section(per_bug, "Per bug (secondary; each bug takes its representative's result)")
    walls = [b for b, r in rows.items() if r["new"]["stop"] == "wall"]
    print(f"\nNew shrinker inputs that hit the 300 s wall stop: {walls or 'none'}")
    fails = [(b, r["new"]["final_verdict"], r["new"]["stop"]) for b, r in rows.items() if not r["new"]["success"]]
    print(f"New shrinker failures (bug, final verdict, stop): {fails or 'none'}")
    ofails = [(b, r["old"]["verdict"], r["old"]["exit"]) for b, r in rows.items() if r["old"]["verdict"] != "WA"]
    print(f"Old shrinker failures under the predicate (bug, verdict, exit): {ofails or 'none'}")
    print("\n#### New shrinker after/floor (tokens) median by population (distinct inputs within each population)\n")
    print("| problem | " + " | ".join(["pilot-random-capture", "pilot-tape-noshare", "pilot-tape-rwlock", "v1-hunt", "v1-hunt-focus", "v1-gallery"]) + " |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for p in FOCUS_PROBLEMS:
        cells = []
        for pop in ("pilot-random-capture", "pilot-tape-noshare", "pilot-tape-rwlock", "v1-hunt", "v1-hunt-focus", "v1-gallery"):
            reps = {r for b, r in rep.items() if rows[r]["problem"] == p and population(b) == pop}
            v = [rows[r]["new"]["after"]["tokens"] / FLOOR[p][0] for r in sorted(reps)]
            cells.append(f"{quant(v, 50):.2f} (n={len(v)})" if v else "-")
        print(f"| {p} | " + " | ".join(cells) + " |")


def population(bid):
    kind = bid.split("__")[0]
    if kind == "pilot":
        return "pilot-" + bid.split("__")[2].split("_w")[0]
    return {"hunt": "v1-hunt", "hunt-focus": "v1-hunt-focus", "gallery": "v1-gallery"}[kind]


if __name__ == "__main__":
    main()
