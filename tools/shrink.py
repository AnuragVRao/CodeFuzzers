#!/usr/bin/env python3
"""Generator-space shrinker: finds a smaller failing recipe (variant, size, seed) for a bug.
Usage: python3 tools/shrink.py <problem> <bug-dir> [--workers W] [--budget 4000] [--seed 7]
Each round the main thread draws 64 candidates (same variant, log-uniform smaller size, fresh
seed), evaluates them in parallel, and processes results in candidate order, so the outcome is
identical for any W. Writes <bug-dir>/shrunk/{input,recipe,ref_out,fast_out}.txt + info.json.
"""
import argparse, json, math, os, random, subprocess, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import problems, repro

BATCH, PATIENCE = 64, 8


def read_recipe(path):
    r = dict(l.split(None, 1) for l in path.read_text().splitlines() if l.strip())
    return dict(variant=int(r["variant"]), size=int(r["size"]), seed=int(r["seed"]))


def stats(text):
    return dict(bytes=len(text.encode()), lines=len(text.splitlines()))


def shrink(name, recipe, input_text, workers, budget, seed):
    rng = random.Random(seed)
    best = dict(recipe, input=input_text)
    trace, used, rnd, stale = [[0, best["size"]]], 0, 0, 0

    def evaluate(c):
        outcome, text = problems.run_test(name, c["variant"], c["size"], c["seed"], "bug")
        return dict(c, outcome=outcome, input=text)

    def best_of(results):
        """Failing result with the smallest (size, bytes), earliest candidate on ties."""
        failing = [r for r in results if r["outcome"] in problems.BUGS]
        return min(failing, key=lambda r: (r["size"], len(r["input"].encode())), default=None)

    with ThreadPoolExecutor(workers) as ex:
        while best["size"] > 1 and stale < PATIENCE and used < budget:
            rnd += 1
            m = best["size"] - 1
            cands = [dict(variant=best["variant"], size=min(m, int(math.exp(rng.uniform(0, math.log(m + 1))))),
                          seed=rng.randrange(1, 2**63)) for _ in range(min(BATCH, budget - used))]
            results = list(ex.map(evaluate, cands))  # map() keeps candidate order
            used += len(cands)
            found = best_of(results)
            if found:
                best, stale = found, 0
            else:
                stale += 1
            trace.append([rnd, best["size"]])
        # polish: more seeds at the final size, keep the failing input with the fewest bytes
        cands = [dict(variant=best["variant"], size=best["size"], seed=rng.randrange(1, 2**63)) for _ in range(BATCH)]
        results = list(ex.map(evaluate, cands))
        used += len(cands)
        found = best_of(results)
        if found and len(found["input"].encode()) < len(best["input"].encode()):
            best = found
    return best, trace, used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("problem")
    ap.add_argument("bug_dir", type=Path)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--budget", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    recipe = read_recipe(a.bug_dir / "recipe.txt")
    original = (a.bug_dir / "input.txt").read_text(errors="replace")
    t0 = time.time()
    best, trace, used = shrink(a.problem, recipe, original, a.workers, a.budget, a.seed)
    wall = time.time() - t0

    out = a.bug_dir / "shrunk"
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.txt").write_text(best["input"])
    (out / "recipe.txt").write_text(f"variant {best['variant']}\nsize {best['size']}\nseed {best['seed']}\n")
    verifier = problems.ROOT / "build" / a.problem / "verifier"
    with open(out / "input.txt", "rb") as f:
        verifier_ok = subprocess.run([str(verifier)], stdin=f, capture_output=True).returncode == 0
    c = repro.check_input(a.problem, out / "input.txt")
    (out / "ref_out.txt").write_bytes(c["out_ref"])
    (out / "fast_out.txt").write_bytes(c["out_fast"])
    info = dict(problem=a.problem,
                original=dict(size=recipe["size"], seed=recipe["seed"], **stats(original)),
                shrunk=dict(size=best["size"], seed=best["seed"], **stats(best["input"])),
                trace=trace, tests_used=used, workers=a.workers, wall_s=round(wall, 3),
                verifier_ok=verifier_ok, mismatch_ok=c["verdict"].startswith("MISMATCH"))
    (out / "info.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"{a.problem}: size {recipe['size']} -> {best['size']}, bytes {info['original']['bytes']} -> "
          f"{info['shrunk']['bytes']}, {used} tests, {wall:.1f}s, verifier_ok={verifier_ok}, "
          f"mismatch_ok={info['mismatch_ok']} ({c['verdict']})")
    return 0 if verifier_ok and info["mismatch_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
