#!/usr/bin/env python3
"""Bug gallery: for every problem, hunt its planted bug with build/fuzzer (rwlock, 20 pinned
workers, 30 s, seed 1) into results/bugs/<problem>/, then shrink it with tools/shrink.py.
Problems whose results/bugs/<problem>/shrunk/info.json exists are skipped (resumable).
Writes results/bugs/gallery.json (shrink info + bugs.json metadata) and prints a summary table.
Usage: python3 tools/bug_gallery.py
"""
import json, subprocess, sys, time
import problems
from run import CPU_ORDER, problem_config

ROOT = problems.ROOT
BUGS_DIR = ROOT / "results" / "bugs"
WORKERS = 20


def hunt_and_shrink(name, cfg):
    d = BUGS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    c = cfg[name]
    cmd = [str(ROOT / "build/fuzzer"), "--build", str(ROOT / "build" / name), "--checker", c["checker"],
           "--max-size", str(c["max_size"]), "--variants", str(c["variants"]), "--fast", "bug", "--mode", "hunt",
           "--strategy", "rwlock", "--workers", str(WORKERS), "--cpus", ",".join(map(str, CPU_ORDER[:WORKERS])),
           "--time-limit", "30", "--seed", "1", "--out", str(d / "hunt.json"), "--bug-dir", str(d)]
    subprocess.run(cmd, check=True)
    bug = json.loads((d / "hunt.json").read_text())["first_bug"]
    if bug is None:
        print(f"{name}: no bug found in 30 s")
        return
    subprocess.run([sys.executable, str(ROOT / "tools/shrink.py"), name, str(d), "--workers", str(WORKERS)])


def main():
    cfg = problem_config()
    meta = {b["problem"]: b for b in json.loads((problems.DATASET / "bugs.json").read_text())}
    t0 = time.time()
    for p in problems.load():
        if not (BUGS_DIR / p["name"] / "shrunk" / "info.json").exists():
            hunt_and_shrink(p["name"], cfg)
    gallery = []
    for p in problems.load():
        f = BUGS_DIR / p["name"] / "shrunk" / "info.json"
        m = meta[p["name"]]
        extra = {k: m[k] for k in ("tier", "kind", "category", "description", "trigger")}
        gallery.append(dict(json.loads(f.read_text()), **extra) if f.exists() else dict(problem=p["name"], found=False, **extra))
    (BUGS_DIR / "gallery.json").write_text(json.dumps(gallery, indent=2) + "\n")

    print(f"\n{'problem':42} {'tier':4} {'size':>11} {'bytes':>13} {'verifier':>8} {'mismatch':>8} {'tests':>5} {'wall_s':>6}")
    for g in gallery:
        if "shrunk" not in g:
            print(f"{g['problem']:42} {g['tier']:4} {'no bug found':>11}")
            continue
        o, s = g["original"], g["shrunk"]
        print(f"{g['problem']:42} {g['tier']:4} {o['size']:>4} → {s['size']:<4} {o['bytes']:>6} → {s['bytes']:<5}"
              f" {str(g['verifier_ok']):>8} {str(g['mismatch_ok']):>8} {g['tests_used']:>5} {g['wall_s']:>6.1f}")
    bad = [g["problem"] for g in gallery if not (g.get("verifier_ok") and g.get("mismatch_ok"))]
    print(f"\n{len(gallery)} problems, {len(gallery) - len(bad)} fully validated; not validated: {bad or 'none'}"
          f"  (total {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
