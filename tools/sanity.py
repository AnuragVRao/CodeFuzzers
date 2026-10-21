#!/usr/bin/env python3
"""Sanity check: for every problem, gen -> {fast, brute} -> compare, over seeds 1..N.

Usage: python3 tools/sanity.py [--seeds 50] [--size S | --sizes 5,20,max] [--fast sol|sol_bug] [--only NAME]
S is an integer or "max" (max_size from fuzz_config.json); sizes are clamped to max_size.
Exit code 1 if any WA/RE/TLE.
"""
import argparse, json, os, shutil, subprocess, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import problems

BUILD = problems.ROOT / "build" / "plain"
TMP = Path("/dev/shm/cf_sanity")
TIMEOUT = 5
CONFIG = json.loads((problems.ROOT / "fuzz_config.json").read_text())
BUGS = ("WA", "RE", "TLE")


def build(p, fast):
    out = BUILD / p["name"]
    fl = problems.flags(p["dir"])
    bins = {v: problems.compile(p["dir"] / "gen" / f"{v}.cpp", out / v, fl) for v in p["variants"]}
    for name in (fast, "brute", "checker"):
        bins[name] = problems.compile(p["dir"] / f"{name}.cpp", out / name, fl)
    bins["fast"] = bins[fast]
    return bins


def run(cmd, inp, out):
    """Run cmd with stdin/stdout files. Returns (returncode or None on timeout, ms)."""
    t0 = time.perf_counter()
    with open(inp, "rb") as fi, open(out, "wb") as fo:
        try:
            rc = subprocess.run(cmd, stdin=fi, stdout=fo, stderr=subprocess.DEVNULL, timeout=TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            rc = None
    return rc, (time.perf_counter() - t0) * 1000


def same(p, bins, inp, out, ans):
    if p["checker_kind"] == "custom":
        r = subprocess.run([str(bins["checker"]), str(inp), str(out), str(ans)], capture_output=True)
        return r.returncode == 0
    return out.read_bytes().split() == ans.read_bytes().split()


def test(p, bins, size, seed):
    """One test -> (outcome, fast_ms, brute_ms); outcome per CLAUDE.md 'Outcome of one test'."""
    base = TMP / f"{p['name']}.{size}.{seed}"
    inp, out, ans = (base.with_suffix(base.suffix + x) for x in (".in", ".out", ".ans"))
    try:
        gen_cmd = [str(bins["generator"]), str(seed)] + ([str(size)] if size is not None else [])
        with open(inp, "wb") as f:
            try:
                g = subprocess.run(gen_cmd, stdout=f, stderr=subprocess.DEVNULL, timeout=TIMEOUT).returncode
            except subprocess.TimeoutExpired:
                g = None
        if g != 0:
            return "gen_skip", 0, 0
        rb, mb = run([str(bins["brute"])], inp, ans)
        if rb != 0:
            return "invalid", 0, mb
        rf, mf = run([str(bins["fast"])], inp, out)
        kind = "TLE" if rf is None else "RE" if rf != 0 else "ok" if same(p, bins, inp, out, ans) else "WA"
        return kind, mf, mb
    finally:
        for f in (inp, out, ans):
            f.unlink(missing_ok=True)


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
    with ThreadPoolExecutor() as ex:
        bins = list(ex.map(lambda p: build(p, a.fast), probs))
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True)
    jobs = [(p, b, s, seed) for p, b in zip(probs, bins) for s in sizes for seed in range(1, a.seeds + 1)]
    t0 = time.time()
    with ThreadPoolExecutor(os.cpu_count()) as ex:
        results = list(ex.map(lambda j: test(j[0], j[1], resolve(j[2], j[0]["name"]), j[3]), jobs))
    shutil.rmtree(TMP, ignore_errors=True)

    stats = {(p["name"], s): Counter() for p in probs for s in sizes}
    ms = {p["name"]: [0.0, 0.0] for p in probs}
    for (p, _, s, _), (kind, mf, mb) in zip(jobs, results):
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
