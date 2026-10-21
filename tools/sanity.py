#!/usr/bin/env python3
"""Sanity check: for every problem, gen -> {fast, brute} -> compare, over seeds 1..N.

Usage: python3 tools/sanity.py [--seeds 50] [--size S | --sizes 5,20,max] [--fast sol|sol_bug] [--only NAME]
S is an integer or "max" (max_size from fuzz_config.json); sizes are clamped to max_size.
Exit code 1 if any WA/RE/TLE.
"""
import argparse, json, os, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import problems

CONFIG = json.loads((problems.ROOT / "fuzz_config.json").read_text())
BUGS = problems.BUGS


def test(p, size, seed, fast):
    """One test -> (outcome, fast_ms, brute_ms), via the shared problems.run_test (variant 0)."""
    times = {}
    kind, _ = problems.run_test(p, 0, size, seed, fast, times)
    return kind, times.get("fast_ms", 0), times.get("brute_ms", 0)


def resolve(size, name):
    """None (generator default), "max" or an int -> value clamped to max_size."""
    cap = CONFIG[name]["max_size"]
    return None if size is None else cap if size == "max" else min(int(size), cap)


def bug_rate(c):
    valid = c["ok"] + sum(c[b] for b in BUGS)
    return 100 * sum(c[b] for b in BUGS) / valid if valid else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--size", default=None, help='integer or "max"')
    ap.add_argument("--sizes", default=None, help="comma list, e.g. 5,20,max")
    ap.add_argument("--fast", choices=["sol", "sol_bug"], default="sol")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    sizes = a.sizes.split(",") if a.sizes else [a.size]

    probs = [p for p in problems.load() if a.only in (None, p["name"])]
    assert probs, f"unknown problem {a.only}"
    with ThreadPoolExecutor() as ex:  # compile up front so compile time is not in the timed part
        list(ex.map(lambda p: problems.plain_bins(p, a.fast), probs))
    jobs = [(p, s, seed) for p in probs for s in sizes for seed in range(1, a.seeds + 1)]
    t0 = time.time()
    with ThreadPoolExecutor(os.cpu_count()) as ex:
        results = list(ex.map(lambda j: test(j[0], resolve(j[1], j[0]["name"]), j[2], a.fast), jobs))

    stats = {(p["name"], s): Counter() for p in probs for s in sizes}
    ms = {p["name"]: [0.0, 0.0] for p in probs}
    for (p, s, _), (kind, mf, mb) in zip(jobs, results):
        stats[p["name"], s][kind] += 1
        ms[p["name"]] = [max(ms[p["name"]][0], mf), max(ms[p["name"]][1], mb)]

    cols = ["ok", *BUGS, "invalid", "gen_skip", "max_sol_ms", "max_brute_ms"]
    w = max(len(p["name"]) for p in probs)
    tot = Counter()
    print(f"{'problem':<{w}} | " + " | ".join(cols))
    for p in probs:
        c = sum((stats[p["name"], s] for s in sizes), Counter())
        tot += c
        vals = [c[k] for k in cols[:6]] + [f"{x:.1f}" for x in ms[p["name"]]]
        print(f"{p['name']:<{w}} | " + " | ".join(f"{v:>{len(k)}}" for k, v in zip(cols, vals)))
    print(f"\n{len(probs)} problems, fast={a.fast}, seeds 1..{a.seeds}, sizes={sizes}: " +
          ", ".join(f"{k}={tot[k]}" for k in cols[:6]) + f"  ({time.time() - t0:.1f}s)")

    if a.sizes:
        heads = [f"bugs@{s}" for s in sizes]
        print(f"\n{'problem':<{w}} | " + " | ".join(heads) + "   (% of valid tests)")
        for p in probs:
            print(f"{p['name']:<{w}} | " + " | ".join(
                f"{bug_rate(stats[p['name'], s]):>{len(h) - 1}.1f}%" for s, h in zip(sizes, heads)))
    sys.exit(1 if any(tot[b] for b in BUGS) else 0)


if __name__ == "__main__":
    main()
