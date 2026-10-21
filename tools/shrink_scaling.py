#!/usr/bin/env python3
"""Measures shrinker scaling: runs tools/shrink.py on gallery bugs with W = 1, 2, 4, 8, 20 workers,
3 repeats each, on copies of results/bugs/<problem>/ in a temp dir (the gallery is not touched).
Writes results/shrink_scaling.csv (problem, workers, repeat, wall_s, tests_used) and prints the
median wall time and speed-up vs W=1 per problem.
Usage: python3 tools/shrink_scaling.py
"""
import csv, json, shutil, statistics, subprocess, sys, tempfile
from pathlib import Path
import problems

PROBLEMS = ["connected_components_of_complement_graph", "vertex_set_path_composite", "rectangle_sum"]
WORKERS, REPEATS = [1, 2, 4, 8, 20], 3
OUT = problems.ROOT / "results" / "shrink_scaling.csv"


def main():
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for p in PROBLEMS:
            src = problems.ROOT / "results" / "bugs" / p
            for w in WORKERS:
                for r in range(REPEATS):
                    d = Path(tmp) / f"{p}_w{w}_r{r}"
                    d.mkdir()
                    for f in ("input.txt", "recipe.txt"):
                        shutil.copy(src / f, d / f)
                    subprocess.run([sys.executable, str(problems.ROOT / "tools/shrink.py"), p, str(d), "--workers", str(w)],
                                   check=True, capture_output=True)
                    info = json.loads((d / "shrunk" / "info.json").read_text())
                    rows.append(dict(problem=p, workers=w, repeat=r, wall_s=info["wall_s"], tests_used=info["tests_used"]))
                    print(f"{p} W={w} r={r}: {info['wall_s']:.2f}s, {info['tests_used']} tests", flush=True)
    with open(OUT, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["problem", "workers", "repeat", "wall_s", "tests_used"])
        wr.writeheader()
        wr.writerows(rows)

    print(f"\nwrote {len(rows)} rows to {OUT.relative_to(problems.ROOT)}\n")
    print(f"{'problem':42} " + " ".join(f"{'W=' + str(w):>12}" for w in WORKERS))
    for p in PROBLEMS:
        med = {w: statistics.median(r["wall_s"] for r in rows if r["problem"] == p and r["workers"] == w) for w in WORKERS}
        print(f"{p:42} " + " ".join(f"{med[w]:5.2f}s {med[1] / med[w]:4.1f}x" for w in WORKERS))


if __name__ == "__main__":
    main()
