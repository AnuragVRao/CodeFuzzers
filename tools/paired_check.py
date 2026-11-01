#!/usr/bin/env python3
"""POST-HOC sensitivity analysis of the hunt experiments: run census and block-paired tests.
The pre-registered analyses (tools/aggregate.py hunt_tests, tools/v3_report.py H1, the pilot criterion) remain the
primary results; this script does not change them.
Reads results/raw/<exp>/<problem>/<arm>_w<W>_k0_f0_r<R>.json for exp = hunt, hunt-focus, pilot, v3.
  census    = per cell (exp, problem, arm, workers): expected vs actual n and the set of repeats; found; censored =
              no bug and wall_s >= config.time_limit; infra = no bug and wall_s < time_limit (pilot Amendment 1).
              Counted from first_bug / wall_s / time_limit in each run JSON, never from inf values.
  seed check = config.seed == base + repeat for every run (base 1000 hunt and hunt-focus, 5000 pilot, 6000 v3) and
              block_seed == base + repeat where present; so every arm of block r ran with the same seed. An
              experiment that fails the check is not paired.
  pairing   = arm a and arm b of the same (problem, workers, repeat); tests-to-bug = first_bug.tests_before + 1.
  paired test = scipy.stats.wilcoxon on d = ln(tests_b / tests_a), zero_method "wilcox" (pairs with d = 0 dropped;
              their count is printed), same sidedness as the original test (two-sided; v3 H1: one-sided, b < a);
              Holm within the original family. Spearman rho of (tests_a, tests_b) shows how strongly blocks pair.
  estimand  = median over blocks of the paired ratio tests_b / tests_a (NOT the ratio of medians in the frozen
              tables); 95% block-bootstrap percentile CI (resample blocks, 2,000 resamples, fixed seed).
  families  = exploratory (hunt: 11 problems x workers 1/8/20 x {random vs noshare, noshare vs rwlock}),
              confirmatory (hunt-focus, 6), v3 H1 (vp-noshare vs vp-rwlock, 3), pilot (tape arms vs random-capture,
              6; the pilot pre-registered a median-ratio criterion, not a test, so its p values are descriptive).
Usage: python3 tools/paired_check.py [--selftest]   (exit 1 on a census or seed-check failure)
"""
import json, math, re, sys, warnings
from collections import defaultdict
import numpy as np
from scipy.stats import spearmanr, wilcoxon
import problems
from aggregate import holm
from run import FOCUS_PROBLEMS, PILOT_ARMS, V3_ARMS, V3_PROBLEMS, hard_problems

RAW = problems.ROOT / "results" / "raw"
NAME = re.compile(r"^(?P<arm>.+)_w(?P<w>\d+)_k0_f0_r(?P<r>\d+)\.json$")
ZERO_METHOD = "wilcox"
SEED = 20261101


def experiments():
    """exp -> (seed base, expected repeats, {(problem, arm, workers)}, [(family, problem, workers, a, b, alternative)])."""
    hard = hard_problems()[0]
    hunt_cmp = [("random", "noshare"), ("noshare", "rwlock")]
    return {
        "hunt": (1000, 30, {(p, s, w) for p in hard for s in ("random", "noshare", "rwlock") for w in (1, 8, 20)},
                 [("exploratory", p, w, a, b, "two-sided") for p in sorted(hard) for w in (1, 8, 20) for a, b in hunt_cmp]),
        "hunt-focus": (1000, 100, {(p, s, 8) for p in FOCUS_PROBLEMS for s in ("random", "noshare", "rwlock")},
                       [("confirmatory", p, 8, a, b, "two-sided") for p in sorted(FOCUS_PROBLEMS) for a, b in hunt_cmp]),
        "pilot": (5000, 200, {(p, s, 8) for p in FOCUS_PROBLEMS for s in PILOT_ARMS},
                  [("pilot (descriptive)", p, 8, "random-capture", b, "two-sided") for p in sorted(FOCUS_PROBLEMS)
                   for b in ("tape-noshare", "tape-rwlock")]),
        "v3": (6000, 100, {(p, s, 8) for p in V3_PROBLEMS for s in V3_ARMS},
               [("v3 H1", p, 8, "vp-noshare", "vp-rwlock", "less") for p in sorted(V3_PROBLEMS)]),
    }


def load(exp):
    runs = []
    for f in sorted((RAW / exp).glob("*/*.json")):
        m = NAME.match(f.name)
        if not m:
            continue
        d = json.loads(f.read_text())
        bug = d.get("first_bug")
        runs.append(dict(problem=f.parent.name, arm=m["arm"], w=int(m["w"]), r=int(m["r"]), seed=d["config"]["seed"],
                         block_seed=d.get("block_seed"), limit=d["config"]["time_limit"], wall=d["wall_s"],
                         found=bug is not None, ttb=bug["tests_before"] + 1 if bug else None))
    return runs


def census(runs, cells, reps):
    """[(cell, n, found, censored, infra, ok)]; ok = the cell has exactly repeats 0..reps-1."""
    g = defaultdict(list)
    for x in runs:
        g[(x["problem"], x["arm"], x["w"])].append(x)
    out = []
    for c in sorted(cells | set(g)):
        xs = g.get(c, [])
        cens = sum(not x["found"] and x["wall"] >= x["limit"] for x in xs)
        infra = sum(not x["found"] and x["wall"] < x["limit"] for x in xs)
        ok = c in cells and sorted(x["r"] for x in xs) == list(range(reps))
        out.append((c, len(xs), sum(x["found"] for x in xs), cens, infra, ok))
    return out


def seed_errors(runs, base):
    return [x for x in runs if x["seed"] != base + x["r"] or x["block_seed"] not in (None, base + x["r"])]


def paired(ta, tb, alternative, seed, n_boot=2000):
    """Paired statistics of tests_b vs tests_a (same blocks): dict(n, zeros, rho, p, median_ratio, ci_lo, ci_hi)."""
    a, b = np.array(ta, dtype=float), np.array(tb, dtype=float)
    d = np.log(b / a)
    zeros = int((d == 0).sum())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = float(wilcoxon(d, zero_method=ZERO_METHOD, alternative=alternative).pvalue) if zeros < len(d) else 1.0
        rho = float(spearmanr(a, b)[0])
    ratio = b / a
    boot = np.median(ratio[np.random.default_rng(seed).integers(0, len(ratio), (n_boot, len(ratio)))], axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return dict(n=len(d), zeros=zeros, rho=rho, p=p, median_ratio=float(np.median(ratio)), ci_lo=float(lo), ci_hi=float(hi))


def analyse(runs, comparisons, seed0):
    """Rows of paired statistics with p_holm per family; refuses (ValueError) a pair with a censored run."""
    by = {(x["problem"], x["arm"], x["w"], x["r"]): x for x in runs}
    rows = []
    for i, (fam, p, w, a, b, alt) in enumerate(comparisons):
        reps = sorted(r for (pp, arm, ww, r) in by if (pp, arm, ww) == (p, a, w) and (p, b, w, r) in by)
        xa, xb = [by[(p, a, w, r)] for r in reps], [by[(p, b, w, r)] for r in reps]
        if not all(x["found"] for x in xa + xb):
            raise ValueError(f"{p} {a}/{b} w{w}: censored run in a pair; the log-ratio test needs finite values")
        rows.append(dict(family=fam, problem=p, w=w, a=a, b=b, alternative=alt,
                         **paired([x["ttb"] for x in xa], [x["ttb"] for x in xb], alt, seed0 + i)))
    for fam in {r["family"] for r in rows}:
        sel = [r for r in rows if r["family"] == fam]
        for r, ph in zip(sel, holm([r["p"] for r in sel])):
            r["p_holm"] = ph
    return rows


def report():
    print("POST-HOC sensitivity analysis; pre-registered results remain primary.\n")
    print(f"zero_method = {ZERO_METHOD!r}; estimand = median of paired ratios (b / a) over blocks; "
          f"95% block-bootstrap CI, 2,000 resamples, seed {SEED} + comparison index\n")
    failed, all_rows = False, []
    for k, (exp, (base, reps, cells, comps)) in enumerate(experiments().items()):
        runs = load(exp)
        cen = census(runs, cells, reps)
        bad = [c for c in cen if not c[5]]
        tot = lambda i: sum(c[i] for c in cen)
        print(f"## {exp}: {len(runs)} runs, expected {len(cells)} cells x {reps} = {len(cells) * reps}; "
              f"found {tot(2)}, censored {tot(3)}, infra {tot(4)}; cells with n != {reps}: {len(bad)}")
        for c, n, found, cens, infra, _ in bad:
            print(f"   MISMATCH {c}: n = {n} (expected {reps if c in cells else 0})")
        errs = seed_errors(runs, base)
        print(f"   seed check (seed == {base} + repeat, block_seed where present): "
              f"{'OK' if not errs else f'FAIL ({len(errs)} runs)'}")
        failed |= bool(bad or errs)
        if exp != "hunt":  # the hunt's 99 cells are summarised above; mismatches are always listed
            print(f"\n| problem | arm | W | expected n | n | found | censored | infra |\n|---|---|---:|---:|---:|---:|---:|---:|")
            for (p, a, w), n, found, cens, infra, _ in cen:
                print(f"| {p} | {a} | {w} | {reps} | {n} | {found} | {cens} | {infra} |")
            print()
        if bad or errs:
            print("   not paired\n")
            continue
        all_rows += analyse(runs, comps, SEED + 1000 * k)
    for fam in dict.fromkeys(r["family"] for r in all_rows):
        sel = [r for r in all_rows if r["family"] == fam]
        print(f"\n### {fam} ({len(sel)} comparisons, Holm over {len(sel)})\n")
        print("| problem | W | b / a | alt | n | zeros | rho | median paired ratio [95% CI] | p (Wilcoxon) | p_Holm |")
        print("|---|---:|---|---|---:|---:|---:|---|---:|---:|")
        for r in sel:
            print(f"| {r['problem']} | {r['w']} | {r['b']} / {r['a']} | {r['alternative']} | {r['n']} | {r['zeros']} | "
                  f"{r['rho']:.2f} | {r['median_ratio']:.2f} [{r['ci_lo']:.2f}, {r['ci_hi']:.2f}] | {r['p']:.3g} | {r['p_holm']:.3g} |")
        sig = [r for r in sel if r["p_holm"] < 0.05]
        print(f"\n{len(sig)} of {len(sel)} significant after Holm (p_Holm < 0.05)")
    return 1 if failed else 0


def synth_pairs(ratio, rng, n=100, median=300):
    """Correlated paired tests-to-bug: a shared lognormal block effect times geometric noise; b's median x ratio."""
    block = rng.lognormal(0, 0.5, n)
    a = np.maximum(1, np.round(block * rng.geometric(math.log(2) / median, n)))
    b = np.maximum(1, np.round(block * rng.geometric(min(1, math.log(2) / (median * ratio)), n)))
    return a, b


def selftest():
    ok = True
    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(f"{name}: {'PASS' if cond else 'FAIL'}")
    rng = np.random.default_rng(1)
    s1, s0 = paired(*synth_pairs(0.5, rng), "two-sided", 1), paired(*synth_pairs(1.0, rng), "two-sided", 2)
    check(f"fixed data, ratio 0.5: p = {s1['p']:.2g} < 0.01, median paired ratio {s1['median_ratio']:.2f} < 1", s1["p"] < 0.01 and s1["median_ratio"] < 1)
    check(f"fixed data, ratio 1.0: p = {s0['p']:.2g} > 0.05", s0["p"] > 0.05)
    rate = lambda ratio, seed: np.mean([paired(*synth_pairs(ratio, np.random.default_rng(seed + i)), "two-sided", i, 200)["p"] < 0.05
                                        for i in range(200)])
    r0, r5 = rate(1.0, 10_000), rate(0.5, 20_000)
    check(f"200 simulations: rejection rate under no effect {r0:.3f} <= 0.08", r0 <= 0.08)
    check(f"200 simulations: rejection rate at ratio 0.5 {r5:.3f} >= 0.90", r5 >= 0.90)
    runs = [dict(problem="p", arm=s, w=8, r=r, seed=1000 + r, block_seed=None, limit=20, wall=1.0, found=True, ttb=10)
            for s in ("x", "y") for r in range(3)]
    check("census: complete synthetic set has no mismatch", all(c[5] for c in census(runs, {("p", "x", 8), ("p", "y", 8)}, 3)))
    cut = [x for x in runs if not (x["arm"] == "y" and x["r"] == 1)]
    check("census: one missing run is a mismatch", sum(not c[5] for c in census(cut, {("p", "x", 8), ("p", "y", 8)}, 3)) == 1)
    timed = [dict(x, found=False, ttb=None, wall=20.5) if x["r"] == 0 else x for x in runs]
    c = census(timed, {("p", "x", 8), ("p", "y", 8)}, 3)
    check("census: no bug and wall >= limit counts as censored, not infra", sum(x[3] for x in c) == 2 and sum(x[4] for x in c) == 0)
    check("seed check: correct seeds pass", not seed_errors(runs, 1000))
    wrong = [dict(x, seed=1005) if x["r"] == 2 and x["arm"] == "x" else x for x in runs]
    check("seed check: one wrong seed is caught", len(seed_errors(wrong, 1000)) == 1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else report())
