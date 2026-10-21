#!/usr/bin/env python3
"""Experiment orchestrator: runs build/fuzzer strictly one run at a time.
Usage: python3 tools/run.py --exp scale|hunt|pinning --preset quick|full [--dry-run]
Each run writes results/raw/<exp>/<problem>/<strategy>_w<W>_k<K>_f<F>_r<R>[_pinX].json and is
skipped if that file exists (resumable); quick presets use <exp>-quick so they never count as full runs. Run r uses --seed 1000+r; worker i is pinned to the
i-th CPU of CPU_ORDER. Scale presets use --recipes random (equal work per test), hunt and pinning
keep guided recipes. Prints the plan size, an ETA, and one progress line per run.
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path
import problems

ROOT = problems.ROOT
RAW = ROOT / "results" / "raw"
FUZZER = ROOT / "build" / "fuzzer"
CPU_ORDER = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
STRATS = ["global", "sharded", "rwlock", "snapshot", "noshare"]
# ETA model: single-worker tests/s and speed-up per worker count (from Step 6, test 5).
BASE_TPS = 1450
SPEEDUP = {1: 1, 2: 2, 4: 3.7, 6: 4.9, 8: 5.9, 12: 7.1, 16: 8.1, 20: 8.6}


def hard_problems():
    bugs = json.loads((problems.DATASET / "bugs.json").read_text())
    return [b["problem"] for b in bugs if b["tier"] == "hard"], {b["problem"]: b for b in bugs}


def plan(exp, preset):
    """List of run dicts: problem, strategy, workers, k, f, repeat, mode, tests, time_limit, pin."""
    runs = []
    recipes = "random" if exp == "scale" else "guided"  # scale: equal work per test for every strategy
    def add(problem, strategy, w, k, f, r, mode, tests=0, limit=0, pin=None):
        runs.append(dict(problem=problem, strategy=strategy, workers=w, k=k, f=f, repeat=r, mode=mode,
                         tests=tests, time_limit=limit, pin=pin, recipes=recipes))
    if exp == "scale":
        full = preset == "full"
        probs = ["range_add_range_min", "zalgorithm", "vertex_add_path_sum"] if full else ["range_add_range_min"]
        workers = [1, 2, 4, 6, 8, 12, 16, 20] if full else [1, 4, 20]
        kfs = [(0, 0), (50, 0.1), (50, 0.5)] if full else [(0, 0), (50, 0.5)]
        reps, tests = (5, 10000) if full else (1, 5000)
        for p in probs:
            for s in STRATS:
                for w in workers:
                    for k, f in kfs:
                        for r in range(reps):
                            add(p, s, w, k, f, r, "scale", tests=tests)
    elif exp == "hunt":
        hard, _ = hard_problems()
        probs, workers, reps = (hard, [1, 8, 20], 30) if preset == "full" else (hard[:2], [8], 3)
        for p in probs:
            for s in ["random", "noshare", "rwlock"]:
                for w in workers:
                    for r in range(reps):
                        add(p, s, w, 0, 0, r, "hunt", limit=20)
    elif exp == "pinning":
        for pin in (1, 0):
            for r in range(5):
                add("range_add_range_min", "global", 8, 0, 0, r, "scale", tests=20000, pin=pin)
    return runs


def out_path(exp, run):
    stem = f"{run['strategy']}_w{run['workers']}_k{run['k']}_f{run['f']}_r{run['repeat']}"
    if run["pin"] is not None:
        stem += f"_pin{run['pin']}"
    return RAW / exp / run["problem"] / f"{stem}.json"


def predict(run, bugs):
    """Rough seconds for one run (start-up + tests / throughput)."""
    tps = BASE_TPS * SPEEDUP.get(run["workers"], run["workers"] * 0.45) * (0.6 if run["k"] else 1)
    if run["mode"] == "scale":
        return 0.3 + run["tests"] / tps
    r = bugs[run["problem"]]["rate"]
    rate = max((r["5"] + r["20"] + r["max"]) / 300, 1e-4)  # rough per-test bug probability
    expected = 1 / rate if run["strategy"] == "random" else 0.7 / rate
    return 0.3 + min(run["time_limit"], expected / tps)


def fmt(sec):
    sec = int(sec)
    return f"{sec // 3600}h{sec % 3600 // 60:02d}m{sec % 60:02d}s"


def command(exp, run, cfg, tmp_out):
    p = cfg[run["problem"]]
    w = run["workers"]
    cpus = "" if run["pin"] == 0 else ",".join(map(str, CPU_ORDER[:w]))
    bug_dir = out_path(exp, run).with_suffix("")  # .../<stem>/ (only created if a bug is found)
    return [str(FUZZER), "--build", str(ROOT / "build" / run["problem"]), "--checker", p["checker"],
            "--max-size", str(p["max_size"]), "--variants", str(p["variants"]),
            "--fast", "sol" if run["mode"] == "scale" else "bug", "--mode", run["mode"],
            "--strategy", run["strategy"], "--recipes", run["recipes"], "--workers", str(w), "--tests", str(run["tests"] or 1),
            "--time-limit", str(run["time_limit"] or 60), "--seed", str(1000 + run["repeat"]),
            "--extra-ops", str(run["k"]), "--write-frac", str(run["f"]), "--cpus", cpus,
            "--out", str(tmp_out), "--bug-dir", str(bug_dir)]


def problem_config():
    """name -> checker/max_size/variants, from the manifest and fuzz_config.json."""
    fuzz_cfg = json.loads((ROOT / "fuzz_config.json").read_text())
    return {p["name"]: dict(checker="custom" if p["checker_kind"] == "custom" else "exact",
                            max_size=fuzz_cfg[p["name"]]["max_size"], variants=len(p["variants"]))
            for p in problems.load()}


def git_info():
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT)
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT)
    return head.stdout.strip(), bool(dirty.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, choices=["scale", "hunt", "pinning"])
    ap.add_argument("--preset", default="quick", choices=["quick", "full"])
    ap.add_argument("--dry-run", action="store_true", help="print the plan and ETA only")
    a = ap.parse_args()

    cfg = problem_config()
    commit, dirty = git_info()
    _, bugs = hard_problems()
    runs = plan(a.exp, a.preset)
    exp_dir = a.exp + ("-quick" if a.preset == "quick" else "")
    todo = [r for r in runs if not out_path(exp_dir, r).exists()]
    eta = sum(predict(r, bugs) for r in todo)
    print(f"{exp_dir}: {len(runs)} runs planned, {len(runs) - len(todo)} already done, "
          f"{len(todo)} to run, ETA {fmt(eta)}")
    if a.dry_run:
        groups = {}
        for r in todo:
            groups.setdefault(r["problem"], []).append(r)
        for p, rs in groups.items():
            print(f"  {p:42} {len(rs):5} runs  ~{fmt(sum(predict(r, bugs) for r in rs))}")
        return 0

    predicted_done = actual_done = 0.0
    for i, run in enumerate(todo, 1):
        out = out_path(exp_dir, run)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".json.tmp")
        t = time.time()
        r = subprocess.run(command(exp_dir, run, cfg, tmp), capture_output=True, text=True)
        dt = time.time() - t
        if r.returncode != 0 or not tmp.exists():
            print(f"[{i}/{len(todo)}] FAILED {out.relative_to(ROOT)}: {r.stderr.strip()[:200]}")
            tmp.unlink(missing_ok=True)
            continue
        d = json.loads(tmp.read_text())
        d["git_commit"], d["git_dirty"] = commit, dirty  # which code produced this result
        tmp.write_text(json.dumps(d, indent=2) + "\n")
        os.replace(tmp, out)  # only complete results count as done
        predicted_done += predict(run, bugs)
        actual_done += dt
        remaining = sum(predict(x, bugs) for x in todo[i:]) * actual_done / predicted_done
        bug = d["first_bug"]
        extra = f"bug {bug['kind']} after {bug['tests_before']} tests" if bug else f"{d['tests_per_sec']:.0f} tests/s"
        print(f"[{i}/{len(todo)}] {run['problem']} {out.stem}: {dt:.1f}s, {extra}; ETA {fmt(remaining)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
