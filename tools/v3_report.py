#!/usr/bin/env python3
"""v3 Step V4 analysis (docs/v3_roadmap.md, frozen at the V3 commit) of results/raw/v3/<problem>/<arm>_w8_*.json.
Primary metric: generated tests-to-bug = tests_before + 1 (skipped duplicates and generator skips are generated
tests); a run without a bug is censored (+inf).
Per problem:
  H1 test  = one-sided Mann-Whitney U, vp-rwlock < vp-noshare, Holm-corrected over the 3 problems;
             H1 is supported if at least 1 problem is significant after Holm (p_Holm < 0.05, in the predicted
             direction); all 3 are reported regardless;
  ratio    = median(vp-rwlock) / median(vp-noshare), 95% percentile bootstrap CI (2,000 resamples,
             aggregate.ratio_ci, seed 20261031 + problem index).
Descriptive only: random-capture medians, quartiles, censoring counts, median wall time to bug, tests/s, foreign-
parent share of all children and of admitted children, foreign-donor share of admitted splice children (pooled
over runs; chance about 7/8 in vp-rwlock, 0 in vp-noshare), origin of the bug-finding child's parent and donor.
Writes results/v3/summary.json and prints markdown tables.
Usage: python3 tools/v3_report.py            (the V4 data)
       python3 tools/v3_report.py --selftest (synthetic data: a known 1.5x effect and a no-effect case)
"""
import argparse, json, math, warnings
import numpy as np
from scipy.stats import mannwhitneyu
import problems
from aggregate import holm, quant, ratio_ci
from run import V3_ARMS, V3_PROBLEMS

RAW = problems.ROOT / "results" / "raw" / "v3"
OUT = problems.ROOT / "results" / "v3" / "summary.json"
SEED = 20261031


def load():
    """problem -> arm -> list of run JSON dicts."""
    return {p: {a: [json.loads(f.read_text()) for f in sorted((RAW / p).glob(f"{a}_w8_k0_f0_r*.json"))] for a in V3_ARMS}
            for p in V3_PROBLEMS}


def share(num, den):
    return num / den if den else None


def analyze(data):
    """data: problem -> arm -> runs. Returns (arm rows, H1 tests, H1 supported, commits)."""
    rows, tests, commits = [], [], set()
    for i, p in enumerate(data):
        g = {}
        for arm, runs in data[p].items():
            commits |= {r.get("git_commit") for r in runs if r.get("git_commit")}
            ttb = [r["first_bug"]["tests_before"] + 1 if r["first_bug"] else math.inf for r in runs]
            wall = [r["first_bug"]["time_s"] if r["first_bug"] else math.inf for r in runs]
            child = [r["first_bug"] for r in runs if r["first_bug"] and r["first_bug"].get("parent_origin", -1) >= 0]
            tot = lambda k: sum(r.get(k, 0) for r in runs)
            g[arm] = ttb
            rows.append(dict(
                problem=p, arm=arm, n=len(runs), censored=sum(map(math.isinf, ttb)),
                median=quant(ttb, 50), q1=quant(ttb, 25), q3=quant(ttb, 75), wall_median_s=quant(wall, 50),
                tests_per_sec_median=float(np.median([r["tests_per_sec"] for r in runs])) if runs else None,
                foreign_pick_share=share(tot("children_foreign"), tot("mutated")),
                foreign_admitted_share=share(tot("adm_foreign"), tot("adm_children")),
                foreign_donor_admitted_share=share(tot("adm_splice_foreign"), tot("adm_splice")),
                bugs_from_children=len(child),
                bugs_child_foreign_parent=sum(b["parent_origin"] != b["worker"] for b in child),
                bugs_from_splice=sum(b.get("donor_origin", -1) >= 0 for b in child),
                bugs_splice_foreign_donor=sum(b.get("donor_origin", -1) >= 0 and b["donor_origin"] != b["worker"] for b in child)))
        a, b = g["vp-noshare"], g["vp-rwlock"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pr = float(mannwhitneyu(b, a, alternative="less").pvalue)
        ma, mb = quant(a, 50), quant(b, 50)
        lo, hi = ratio_ci(a, b, SEED + i)
        tests.append(dict(problem=p, n_noshare=len(a), n_rwlock=len(b), median_noshare=ma, median_rwlock=mb,
                          ratio=mb / ma if math.isfinite(ma) and math.isfinite(mb) else None, ci_lo=lo, ci_hi=hi, p_raw=pr))
    for t, ph in zip(tests, holm([t["p_raw"] for t in tests])):
        t["p_holm"] = ph
    supported = any(t["p_holm"] < 0.05 and t["ratio"] is not None and t["ratio"] < 1 for t in tests)
    return rows, tests, supported, commits


def report(rows, tests, supported):
    num = lambda x: "censored" if x is None or not math.isfinite(x) else f"{x:,.0f}"
    sh = lambda x: "-" if x is None else f"{x:.3f}"
    print("| problem | arm | n | censored | median tests-to-bug | q1 | q3 | median wall s | tests/s | foreign parent (all / admitted) | foreign donor (admitted splices) |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|")
    for r in rows:
        wall = "censored" if not math.isfinite(r["wall_median_s"]) else f"{r['wall_median_s']:.1f}"
        print(f"| {r['problem']} | {r['arm']} | {r['n']} | {r['censored']} | {num(r['median'])} | {num(r['q1'])} | {num(r['q3'])} | "
              f"{wall} | {r['tests_per_sec_median']:,.0f} | {sh(r['foreign_pick_share'])} / {sh(r['foreign_admitted_share'])} | "
              f"{sh(r['foreign_donor_admitted_share'])} |")
    print("\nH1: one-sided Mann-Whitney U (vp-rwlock < vp-noshare), Holm over the 3 problems; censored = +inf")
    print("| problem | median vp-noshare | median vp-rwlock | ratio vp-rwlock / vp-noshare [95% CI] | p (one-sided) | p_Holm |")
    print("|---|---:|---:|---|---:|---:|")
    for t in tests:
        ratio = "-" if t["ratio"] is None else f"{t['ratio']:.2f} [{t['ci_lo']:.2f}, {t['ci_hi']:.2f}]"
        print(f"| {t['problem']} | {num(t['median_noshare'])} | {num(t['median_rwlock'])} | {ratio} | {t['p_raw']:.3g} | {t['p_holm']:.3g} |")
    print(f"\nH1 verdict: {'H1 is supported' if supported else 'H1 is not supported'} "
          "(supported if at least 1 problem is significant after Holm; all 3 are reported regardless).")
    print("\nBug-finding test (descriptive): child of a pool entry / with a foreign parent / from a splice / with a foreign donor")
    for r in rows:
        if r["arm"] != "random-capture":
            print(f"  {r['problem']:27} {r['arm']:11} {r['bugs_from_children']:3} / {r['bugs_child_foreign_parent']:3} / "
                  f"{r['bugs_from_splice']:3} / {r['bugs_splice_foreign_donor']:3}  (of {r['n'] - r['censored']} bugs)")


def synthetic(ratio, seed, n=100, median=60_000, cap=360_000):
    """Fake V4 data: exponential tests-to-bug; vp-rwlock median = ratio x vp-noshare's; runs past cap are censored."""
    rng = np.random.default_rng(seed)
    def runs(med):
        out = []
        for x in rng.exponential(med / math.log(2), n):
            t = int(x) + 1
            fb = None if t > cap else dict(tests_before=t - 1, time_s=t / 10_000, worker=0, parent_origin=-1, donor_origin=-1)
            out.append(dict(first_bug=fb, tests_per_sec=10_000.0, git_commit="synthetic"))
        return out
    return {f"synthetic_{k}": {"vp-noshare": runs(median), "vp-rwlock": runs(median * ratio), "random-capture": runs(median)}
            for k in range(3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        for name, ratio, expect in (("known effect: vp-rwlock median = vp-noshare / 1.5", 1 / 1.5, True),
                                    ("no effect: equal medians", 1.0, False)):
            print(f"=== synthetic, {name} (n = 100 per arm, exponential, censored past 360,000) ===")
            rows, tests, supported, _ = analyze(synthetic(ratio, seed=12345 if expect else 54321))
            report(rows, tests, supported)
            print(f"expected verdict: {'supported' if expect else 'not supported'} -> {'OK' if supported == expect else 'MISMATCH'}\n")
        return
    rows, tests, supported, commits = analyze(load())
    report(rows, tests, supported)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    clean = lambda x: None if isinstance(x, float) and not math.isfinite(x) else x
    OUT.write_text(json.dumps(dict(commits=sorted(commits), h1_supported=supported,
                                   arms=[{k: clean(v) for k, v in r.items()} for r in rows],
                                   h1=[{k: clean(v) for k, v in t.items()} for t in tests]), indent=1) + "\n")


if __name__ == "__main__":
    main()
