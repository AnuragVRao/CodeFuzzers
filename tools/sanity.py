#!/usr/bin/env python3
"""Sanity check: for every problem, gen -> {sol, brute} -> compare, over seeds 1..N.

Usage: python3 tools/sanity.py [--seeds 50] [--size S]
Exit code 1 if any mismatch or timeout.
"""
import argparse, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import problems

BUILD = problems.ROOT / "build" / "plain"
TMP = Path("/dev/shm/cf_sanity")
TIMEOUT = 5


def build(p):
    out = BUILD / p["name"]
    fl = problems.flags(p["dir"])
    bins = {v: problems.compile(p["dir"] / "gen" / f"{v}.cpp", out / v, fl) for v in p["variants"]}
    for key, name in (("fast_solution", "sol"), ("brute", "brute"), ("checker", "checker")):
        bins[name] = problems.compile(p["dir"] / p["files"][key], out / name, fl)
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


def check(p, bins, seeds, size):
    st = dict(ok=0, mismatch=0, gen_skipped=0, timeouts=0, max_sol_ms=0.0, max_brute_ms=0.0, first_bad=None)
    tmp = TMP / p["name"]
    tmp.mkdir(parents=True, exist_ok=True)
    inp, out, ans = tmp / "in.txt", tmp / "sol.txt", tmp / "brute.txt"
    for seed in range(1, seeds + 1):
        gen_cmd = [str(bins["generator"]), str(seed)] + ([str(size)] if size is not None else [])
        with open(inp, "wb") as f:
            try:
                g = subprocess.run(gen_cmd, stdout=f, stderr=subprocess.DEVNULL, timeout=TIMEOUT).returncode
            except subprocess.TimeoutExpired:
                g = None
        if g is None:
            st["timeouts"] += 1
            st["first_bad"] = st["first_bad"] or f"seed {seed}: generator timeout"
            continue
        if g != 0:
            st["gen_skipped"] += 1
            continue
        rs, ms = run([str(bins["sol"])], inp, out)
        rb, mb = run([str(bins["brute"])], inp, ans)
        st["max_sol_ms"] = max(st["max_sol_ms"], ms)
        st["max_brute_ms"] = max(st["max_brute_ms"], mb)
        if rs is None or rb is None:
            st["timeouts"] += 1
            st["first_bad"] = st["first_bad"] or f"seed {seed}: timeout ({'sol' if rs is None else 'brute'})"
        elif rs != 0 or rb != 0 or not same(p, bins, inp, out, ans):
            # a crash of sol or brute counts as a mismatch
            st["mismatch"] += 1
            st["first_bad"] = st["first_bad"] or f"seed {seed}: mismatch (sol rc={rs}, brute rc={rb})"
        else:
            st["ok"] += 1
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--size", type=int, default=None)
    a = ap.parse_args()

    probs = problems.load()
    with ThreadPoolExecutor() as ex:
        bins = list(ex.map(build, probs))
    shutil.rmtree(TMP, ignore_errors=True)
    t0 = time.time()
    with ThreadPoolExecutor() as ex:
        stats = list(ex.map(lambda pb: check(*pb, a.seeds, a.size), zip(probs, bins)))
    shutil.rmtree(TMP, ignore_errors=True)

    cols = ["ok", "mismatch", "gen_skipped", "timeouts", "max_sol_ms", "max_brute_ms"]
    w = max(len(p["name"]) for p in probs)
    print(f"{'problem':<{w}} | " + " | ".join(cols))
    print("-" * (w + 1) + "|" + "|".join("-" * (len(c) + 2) for c in cols))
    for p, s in zip(probs, stats):
        print(f"{p['name']:<{w}} | " + " | ".join(
            f"{s[c]:>{len(c)}.1f}" if c.endswith("ms") else f"{s[c]:>{len(c)}}" for c in cols))
    tot = {c: sum(s[c] for s in stats) for c in cols[:4]}
    print(f"\n{len(probs)} problems, seeds 1..{a.seeds}, size={a.size}: " +
          ", ".join(f"{c}={v}" for c, v in tot.items()) + f"  ({time.time() - t0:.1f}s)")
    for p, s in zip(probs, stats):
        if s["first_bad"]:
            print(f"  {p['name']}: {s['first_bad']}")
    sys.exit(1 if tot["mismatch"] or tot["timeouts"] else 0)


if __name__ == "__main__":
    main()
