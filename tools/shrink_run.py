#!/usr/bin/env python3
"""Runs the Step S shrinkers over a bug set (docs/shrink_plan.md). Read-only on results/raw/ and results/bugs/.
Sets: dev  = the 27 non-focus gallery bugs (results/bugs/<problem>/);
      eval = every focus-problem bug: pilot (results/raw/pilot/), v1 hunt and hunt-focus (results/raw/), and the
             3 focus gallery bugs (results/bugs/).
Modes: --capture-only   stage 0 only (regenerated input hashes to input.txt), matched/total per population
       --shrinker new   tools/shrink.py's v2 shrinker, --jobs bugs in parallel, into OUT/<bug id>/
       --shrinker old   tools/shrink.py --old on a copy of each bug directory (OUT/<bug id>/bug/), seed per bug =
                        int(sha256(bug id)[:8], 16); one bug at a time, its own process pool of --jobs workers
       --replay         cold start: re-judge every OUT/<bug id>/input.txt with fresh processes; it must give the
                        bug's original verdict (info.json original_verdict: WA for every shrunk bug)
Usage: python3 tools/shrink_run.py --set dev|eval [--capture-only | --replay] [--shrinker new|old] [--jobs 16]
                                   [--out results/shrink/<set>[_old]] [--max-evals 2000] [--wall 60]
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import problems, shrink
from run import FOCUS_PROBLEMS

ROOT = problems.ROOT


def bug_set(name):
    """[(bug id, problem, population, bug dir)] in a fixed order."""
    out, bugs = [], ROOT / "results" / "bugs"
    if name == "dev":
        for d in sorted(p for p in bugs.iterdir() if p.is_dir() and p.name not in FOCUS_PROBLEMS):
            out.append((f"gallery__{d.name}", d.name, "dev-gallery", d))
        return out
    for p in FOCUS_PROBLEMS:
        for d in sorted((ROOT / "results/raw/pilot" / p).glob("*_r*/"), key=lambda x: (x.name.split("_w")[0], int(x.name.rsplit("_r", 1)[1]))):
            out.append((f"pilot__{p}__{d.name}", p, "pilot-" + d.name.split("_w")[0], d))
        for exp in ("hunt", "hunt-focus"):
            for d in sorted((ROOT / "results/raw" / exp / p).glob("*/")):
                out.append((f"{exp}__{p}__{d.name}", p, f"v1-{exp}", d))
        out.append((f"gallery__{p}", p, "v1-gallery", bugs / p))
    return out


def capture_one(job):
    bid, problem, pop, d = job
    tmp = Path(f"/dev/shm/cf_capture_{os.getpid()}")
    tmp.mkdir(exist_ok=True)
    try:
        return pop, shrink.capture(problem, d, tmp)[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def new_one(args):
    (bid, problem, pop, d), out, max_evals, wall = args
    info = shrink.shrink_bug(problem, d, out / bid, max_evals, wall)
    return dict(bug=bid, population=pop, **{k: v for k, v in info.items() if k != "bug_dir"})


def old_one(bid, problem, pop, d, out, jobs):
    copy = out / bid / "bug"
    copy.mkdir(parents=True, exist_ok=True)
    for f in ("input.txt", "recipe.txt"):
        shutil.copyfile(d / f, copy / f)
    seed = int(hashlib.sha256(bid.encode()).hexdigest()[:8], 16)
    t0 = time.time()
    r = subprocess.run([sys.executable, str(ROOT / "tools/shrink.py"), "--old", problem, str(copy), "--workers", str(jobs),
                        "--seed", str(seed)], capture_output=True, text=True)
    info = json.loads((copy / "shrunk" / "info.json").read_text()) if (copy / "shrunk" / "info.json").exists() else {}
    return dict(bug=bid, population=pop, problem=problem, seed=seed, exit=r.returncode, wall_s=round(time.time() - t0, 3),
                before=dict(bytes=len((d / "input.txt").read_bytes())), after_bytes=info.get("shrunk", {}).get("bytes"),
                tests_used=info.get("tests_used"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["dev", "eval"], required=True)
    ap.add_argument("--capture-only", action="store_true")
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--shrinker", choices=["new", "old"], default="new")
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--max-evals", type=int, default=2000)
    ap.add_argument("--wall", type=float, default=60.0)
    a = ap.parse_args()
    bugs = bug_set(a.set)
    out = a.out or ROOT / "results" / "shrink" / (a.set + ("_old" if a.shrinker == "old" else ""))
    if a.capture_only:
        with ProcessPoolExecutor(a.jobs) as ex:
            res = list(ex.map(capture_one, bugs, chunksize=8))
        tot, ok = Counter(p for p, _ in res), Counter(p for p, m in res if m)
        for pop in sorted(tot):
            print(f"{pop:22} {ok[pop]:5} / {tot[pop]:5} captured inputs hash to input.txt")
        print(f"{'total':22} {sum(ok.values()):5} / {len(res):5}")
        return 0 if sum(ok.values()) == len(res) else 1
    if a.replay:
        tmp = Path(f"/dev/shm/cf_replay_{os.getpid()}")
        tmp.mkdir(exist_ok=True)
        bad = []
        for bid, problem, _, _ in bugs:
            want = json.loads((out / bid / "info.json").read_text())["original_verdict"]
            v = shrink.Judge(problem, tmp).verdict((out / bid / "input.txt").read_text())
            if v != want:
                bad.append((bid, want, v))
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"cold-start replay: {len(bugs) - len(bad)} / {len(bugs)} final inputs reproduce the original verdict"
              + (f"; mismatches (bug, original, now): {bad}" if bad else ""))
        return 1 if bad else 0
    t0 = time.time()
    if a.shrinker == "new":
        with ProcessPoolExecutor(a.jobs) as ex:
            rows = list(ex.map(new_one, [(b, out, a.max_evals, a.wall) for b in bugs]))
    else:
        rows = [old_one(*b, out, a.jobs) for b in bugs]
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(dict(set=a.set, shrinker=a.shrinker, jobs=a.jobs, max_evals=a.max_evals,
                                                      wall=a.wall, total_wall_s=round(time.time() - t0, 1), bugs=rows), indent=1) + "\n")
    print(f"wrote {out / 'summary.json'} ({len(rows)} bugs, {time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
