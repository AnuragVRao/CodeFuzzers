#!/usr/bin/env python3
"""Flattens every fuzzer result under results/raw/<experiment>/<problem>/*.json into
results/runs.csv, one row per run (config, throughput, coverage, first bug, outcome counts, git
commit/dirty as stamped by run.py, recipes, mean_size, ref_fail and checker_error; empty for older runs
without them). v2 tape metrics (generated, executed, dup_skip, ..., bug_executed_before) are empty for
runs without them. strategy is the arm: the fuzzer's --strategy, except for v2 runs ("tape-<strategy>"
[+"-span"][+"-byte"] for --recipes tape, "random-capture" for --tape-capture), so arms never share a group.
The repeat index and pinning come from the file name (..._r<R>[_pinX].json).
Usage: python3 tools/flatten.py
"""
import csv, json, re
import problems

RAW = problems.ROOT / "results" / "raw"
OUT = problems.ROOT / "results" / "runs.csv"
COLS = ["experiment", "problem", "strategy", "workers", "K", "F", "repeat", "pinned", "wall_s", "tests",
        "tests_per_sec", "cov_features", "pool_entries", "new_cov_reports", "bug_found", "bug_tests_before",
        "bug_time_s", "bug_kind", "recipes", "mean_size", "ok", "WA", "RE", "TLE", "invalid", "gen_skip", "ref_fail",
        "checker_error", "generated", "executed", "dup_skip", "gen_budget_exceeded", "tape_overflow", "mut_changed_input",
        "arena_mb", "arena_bytes", "arena_full", "bug_executed_before", "git_commit", "git_dirty"]
TAPE_METRICS = ["generated", "executed", "dup_skip", "gen_budget_exceeded", "tape_overflow", "mut_changed_input",
                "arena_bytes", "arena_full"]


def arm(c):
    if c.get("recipes") == "tape" and c.get("value_profile") and c.get("splice"):  # v3 arms (docs/v3_roadmap.md)
        return f"vp-{c['strategy']}"
    if c.get("recipes") == "tape":
        return f"tape-{c['strategy']}" + ("-span" if c.get("tape_span") else "") + ("-byte" if c.get("tape_mut") == "byte" else "")
    return "random-capture" if c.get("tape_capture") else c["strategy"]


def main():
    rows = []
    for f in sorted(RAW.glob("*/*/*.json")):
        d = json.loads(f.read_text())
        c, bug = d["config"], d["first_bug"]
        m = re.search(r"_r(\d+)", f.stem)
        rows.append(dict(experiment=f.parent.parent.name, problem=f.parent.name, strategy=arm(c),
                         workers=c["workers"], K=c["extra_ops"], F=c["write_frac"], repeat=int(m[1]),
                         pinned=int(bool(c["cpus"])), wall_s=d["wall_s"], tests=d["tests"],
                         tests_per_sec=d["tests_per_sec"], cov_features=d["cov_features"],
                         pool_entries=d["pool_entries"], new_cov_reports=d["new_cov_reports"],
                         bug_found=int(bug is not None), bug_tests_before=bug["tests_before"] if bug else "",
                         bug_time_s=bug["time_s"] if bug else "", bug_kind=bug["kind"] if bug else "",
                         recipes=c.get("recipes", ""), mean_size=d.get("mean_size", ""),
                         git_commit=d.get("git_commit", ""), git_dirty=int(d.get("git_dirty", False)),
                         arena_mb=c.get("arena_mb", ""), bug_executed_before=bug.get("executed_before", "") if bug else "",
                         **{k: "" if d.get(k) is None else d[k] for k in TAPE_METRICS},
                         **d["outcomes"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT.relative_to(problems.ROOT)}")


if __name__ == "__main__":
    main()
