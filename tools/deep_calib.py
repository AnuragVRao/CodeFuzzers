#!/usr/bin/env python3
"""v3 Step V1 (docs/v3_roadmap.md): mechanical constants and calibration of the deep bugs.
Per problem (Dataset/problems/<g>/<p>/sol_bug_deep.cpp, guards from core/deep_bug.hpp):
  1. sample 2,000 inputs (random.Random(8000): variant, size uniform 1..max_size, 63-bit seed) through the
     build/plain/ generator and a -DCF_GUARD_LOG build of sol_bug_deep -> (g1, g2, g3) per input;
  2. constants for target per-guard pass rate p: C1, C2 = constants whose empirical P(g >= C) is closest to p
     (ties: larger C); M = round(1/p); C3 = residue whose empirical P(g3 mod M == r) is closest to p (ties:
     smaller r). They are written into the #define lines of sol_bug_deep.cpp (never by hand);
  3. trigger check: a hand-written trigger input (TRIGGERS below, built from the constants) passes the verifier,
     sol.cpp is judged ok and sol_bug_deep WA on it;
  4. calibration: random-capture, 8 workers, 10 runs, seeds 7000-7009, 60 s limit; qualifies if the median
     generated tests-to-bug (tests_before + 1, censored = +inf) is in [15,000, 120,000]. One adjustment: p * 2 if
     too slow, p / 2 if too fast, then steps 2-4 again.
Every candidate is recorded in Dataset/bugs_deep.json; fuzzer outputs go to results/deep_calib/<problem>/.
Usage: python3 tools/deep_calib.py <problem> [--p 0.026]
"""
import argparse, json, math, random, re, statistics, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import problems
from run import CPU_ORDER, FUZZER, problem_config

ROOT = problems.ROOT
P0, SAMPLES, SAMPLE_SEED = 0.026, 2000, 8000
BAND = (15_000, 120_000)
CAL_RUNS, CAL_SEED, CAL_LIMIT, WORKERS = 10, 7000, 60, 8
OUT = ROOT / "results" / "deep_calib"
BUGS = ROOT / "Dataset" / "bugs_deep.json"


def lines(*rows):
    return "\n".join(" ".join(map(str, r)) for r in rows) + "\n"


def fix_sum(vals, M, C3, i):
    """Add the smallest non-negative d to vals[i] so that sum(vals) mod M == C3."""
    vals[i] += (C3 - sum(vals)) % M
    return vals


# Hand-written trigger inputs: pass all three guards (g1 >= C1, g2 >= C2, g3 mod M == C3), valid for the verifier,
# and make sol print at least one integer.
TRIGGERS = {
    "range_add_range_min": lambda C1, C2, M, C3: (lambda n: lines(
        (n, 1), fix_sum([C2] + [0] * (n - 1), M, C3, n - 1), (1, 0, n)))(max(C1, 2)),
    "range_affine_range_sum": lambda C1, C2, M, C3: (lambda n: lines(
        (n, 1), fix_sum([C2] + [0] * (n - 1), M, C3, n - 1), (1, 0, n)))(max(C1, 2)),
    "range_set_range_composite": lambda C1, C2, M, C3: (lambda n: lines(
        (n, 1), *[(a, 0) for a in fix_sum([C2] + [1] * (n - 1), M, C3, n - 1)], (1, 0, n, 0)))(max(C1, 2)),
}


def guard_bin(p):
    out = problems.PLAIN / p["name"] / "sol_bug_deep_log"
    fl = [*problems.flags(p["dir"]), "-I", str(ROOT / "core"), "-DCF_GUARD_LOG"]
    return problems.compile(p["dir"] / "sol_bug_deep.cpp", out, fl)


def sample(p):
    """SAMPLES inputs -> list of (g1, g2, g3); generator skips are dropped (and counted)."""
    bins = problems.plain_bins(p, "sol")
    log = guard_bin(p)
    max_size = problems.max_sizes()[p["name"]]["max_size"]
    rng = random.Random(SAMPLE_SEED)
    recipes = [(rng.choice(p["variants"]), rng.randint(1, max_size), rng.getrandbits(63)) for _ in range(SAMPLES)]

    def one(rec):
        v, size, seed = rec
        g = subprocess.run([str(bins[v]), str(seed), str(size)], capture_output=True, timeout=10)
        if g.returncode != 0:
            return None
        r = subprocess.run([str(log)], input=g.stdout, capture_output=True, timeout=10)
        return tuple(int(x) for x in r.stderr.split()[:3])

    with ThreadPoolExecutor(16) as ex:
        got = list(ex.map(one, recipes))
    return [g for g in got if g is not None], sum(g is None for g in got)


def threshold(vals, p):
    """C with empirical P(v >= C) closest to p (ties: larger C) -> (C, rate)."""
    n, best = len(vals), None
    for c in sorted(set(vals)):
        rate = sum(v >= c for v in vals) / n
        key = (abs(rate - p), -c)
        if best is None or key < best[0]:
            best = (key, c, rate)
    return best[1], best[2]


def constants(g, p):
    C1, r1 = threshold([x[0] for x in g], p)
    C2, r2 = threshold([x[1] for x in g], p)
    M = round(1 / p)
    rates = [sum(x[2] % M == r for x in g) / len(g) for r in range(M)]
    C3 = min(range(M), key=lambda r: (abs(rates[r] - p), r))
    return dict(C1=C1, C2=C2, M=M, C3=C3), dict(g1=r1, g2=r2, g3=rates[C3])


def write_constants(p, c):
    f = p["dir"] / "sol_bug_deep.cpp"
    s = f.read_text()
    for k in ("C1", "C2", "M", "C3"):
        s, n = re.subn(rf"^#define CF_{k} .*$", f"#define CF_{k} {c[k]}", s, count=1, flags=re.M)
        assert n == 1, k
    f.write_text(s)


def trigger_check(p, c):
    text = TRIGGERS[p["name"]](c["C1"], c["C2"], c["M"], c["C3"])
    ver = subprocess.run([str(ROOT / "build" / p["name"] / "verifier")], input=text.encode(), capture_output=True)
    deep = problems.compile(p["dir"] / "sol_bug_deep.cpp", problems.PLAIN / p["name"] / "sol_bug_deep",
                            [*problems.flags(p["dir"]), "-I", str(ROOT / "core")])
    b = problems.bundle_for_problem(p, "sol")
    sol_out = problems.check_text(b, text)[0]
    deep_out = problems.check_text(dict(b, fast=str(deep)), text)[0]
    return dict(verifier_ok=ver.returncode == 0, sol=sol_out, deep=deep_out,
                ok=ver.returncode == 0 and sol_out == "ok" and deep_out == "WA")


def calibrate(p, tag):
    cfg = problem_config()[p["name"]]
    out = OUT / p["name"]
    out.mkdir(parents=True, exist_ok=True)
    ttb = []
    for r in range(CAL_RUNS):
        js = out / f"{tag}_s{CAL_SEED + r}.json"
        cmd = [str(FUZZER), "--build", str(ROOT / "build" / p["name"]), "--checker", cfg["checker"],
               "--max-size", str(cfg["max_size"]), "--variants", str(cfg["variants"]), "--fast", "bug_deep",
               "--mode", "hunt", "--strategy", "random", "--tape-capture", "1", "--recipes", "guided",
               "--workers", str(WORKERS), "--tests", "1", "--time-limit", str(CAL_LIMIT), "--seed", str(CAL_SEED + r),
               "--cpus", ",".join(map(str, CPU_ORDER[:WORKERS])), "--out", str(js), "--bug-dir", str(out / f"{tag}_bug{r}")]
        subprocess.run(cmd, check=True, capture_output=True)
        fb = json.loads(js.read_text())["first_bug"]
        ttb.append(fb["tests_before"] + 1 if fb else math.inf)
        print(f"  run {r}: {ttb[-1]}", flush=True)
    s = sorted(ttb)
    q = lambda f: s[min(len(s) - 1, int(f * (len(s) - 1) + 0.5))]
    return dict(median=statistics.median(ttb), q1=q(0.25), q3=q(0.75), censored=sum(map(math.isinf, ttb)),
                tests_to_bug=[x if x != math.inf else None for x in ttb])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("problem")
    ap.add_argument("--p", type=float, default=P0)
    a = ap.parse_args()
    p = problems.get(a.problem)
    g, skips = sample(p)
    print(f"{p['name']}: {len(g)} samples ({skips} generator skips)")
    rounds, pr = [], a.p
    for rnd in range(2):
        c, rates = constants(g, pr)
        infeasible = [k for k, v in rates.items() if not pr / 2 <= v <= 2 * pr]
        rec = dict(p=pr, constants=c, rates=rates)
        print(f" round {rnd}: p={pr} {c} rates={rates}")
        if infeasible:
            rec["reason"] = f"constant_infeasible ({', '.join(infeasible)})"
            rounds.append(rec)
            break
        write_constants(p, c)
        subprocess.run([sys.executable, str(ROOT / "tools/build.py")], check=True, capture_output=True)
        rec["trigger"] = trigger_check(p, c)
        print(f"  trigger: {rec['trigger']}")
        if not rec["trigger"]["ok"]:
            rec["reason"] = "perturbation"
            rounds.append(rec)
            break
        rec["calibration"] = cal = calibrate(p, f"round{rnd}")
        print(f"  median {cal['median']} (q1 {cal['q1']}, q3 {cal['q3']}), censored {cal['censored']}")
        rounds.append(rec)
        if BAND[0] <= cal["median"] <= BAND[1]:
            break
        rec["reason"] = "too_slow" if cal["median"] > BAND[1] else "too_fast"
        pr = pr * 2 if cal["median"] > BAND[1] else pr / 2
    last = rounds[-1]
    qualified = "calibration" in last and BAND[0] <= last["calibration"]["median"] <= BAND[1]
    bugs = json.loads(BUGS.read_text()) if BUGS.exists() else {}
    med = lambda r: None if r.get("calibration") is None or math.isinf(r["calibration"]["median"]) else r["calibration"]["median"]
    for r in rounds:
        if "calibration" in r:
            r["calibration"] = dict(r["calibration"], median=med(r))
    bugs[p["name"]] = dict(qualified=qualified, samples=len(g), generator_skips=skips, band=list(BAND), rounds=rounds)
    BUGS.write_text(json.dumps(bugs, indent=1) + "\n")
    print(f"{p['name']}: {'QUALIFIED' if qualified else 'rejected (' + last.get('reason', '?') + ')'}")


if __name__ == "__main__":
    main()
