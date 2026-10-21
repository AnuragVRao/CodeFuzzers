#!/usr/bin/env python3
"""Flattens every fuzzer result under results/raw/<experiment>/<problem>/*.json into
results/runs.csv, one row per run (config, throughput, coverage, first bug, outcome counts).
The repeat index and pinning come from the file name (..._r<R>[_pinX].json).
Usage: python3 tools/flatten.py
"""
import csv, json, re
import problems

RAW = problems.ROOT / "results" / "raw"
OUT = problems.ROOT / "results" / "runs.csv"
COLS = ["experiment", "problem", "strategy", "workers", "K", "F", "repeat", "pinned", "wall_s", "tests",
        "tests_per_sec", "cov_features", "pool_entries", "new_cov_reports", "bug_found", "bug_tests_before",
        "bug_time_s", "bug_kind", "ok", "WA", "RE", "TLE", "invalid", "gen_skip"]


def main():
    rows = []
    for f in sorted(RAW.glob("*/*/*.json")):
        d = json.loads(f.read_text())
        c, bug = d["config"], d["first_bug"]
        m = re.search(r"_r(\d+)", f.stem)
        rows.append(dict(experiment=f.parent.parent.name, problem=f.parent.name, strategy=c["strategy"],
                         workers=c["workers"], K=c["extra_ops"], F=c["write_frac"], repeat=int(m[1]),
                         pinned=int(bool(c["cpus"])), wall_s=d["wall_s"], tests=d["tests"],
                         tests_per_sec=d["tests_per_sec"], cov_features=d["cov_features"],
                         pool_entries=d["pool_entries"], new_cov_reports=d["new_cov_reports"],
                         bug_found=int(bug is not None), bug_tests_before=bug["tests_before"] if bug else "",
                         bug_time_s=bug["time_s"] if bug else "", bug_kind=bug["kind"] if bug else "",
                         **d["outcomes"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT.relative_to(problems.ROOT)}")


if __name__ == "__main__":
    main()
