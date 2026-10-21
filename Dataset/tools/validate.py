#!/usr/bin/env python3
"""Validate every problem in the CodeFuzzers benchmark suite.

For each problem it
  1. compiles generator(s), verifier, fast solution, brute force and checker,
  2. checks the generator is deterministic (same seed -> identical input),
  3. runs many seeds: generator -> verifier -> {fast solution, brute force} -> checker,
     and records mismatches, invalid inputs, timeouts, input sizes and run times.

Usage:  python3 tools/validate.py [--seeds 150] [--only NAME ...] [--budget SECONDS]
Results are appended to tools/validation_results.jsonl (resumable: finished problems are skipped).
"""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "_build"
CXX = ["g++", "-std=c++17", "-w", "-I", str(ROOT / "common")]
SIZES = [4, 8, 16, 32]          # size knob values cycled through by authored generators
TIMEOUT = 5


def compile_cached(src: Path, extra_inc: Path, opt: str, tag: str) -> Path:
    h = hashlib.md5(src.read_bytes() + opt.encode()).hexdigest()[:10]
    out = BUILD / f"{tag}_{h}"
    if not out.exists():
        r = subprocess.run(CXX + [opt, "-I", str(extra_inc), "-o", str(out), str(src)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"compile failed: {src.name}\n{r.stderr[-500:]}")
    return out


def run(cmd, stdin=None, stdout=None):
    t0 = time.time()
    r = subprocess.run(cmd, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, timeout=TIMEOUT)
    return r, (time.time() - t0) * 1000


def validate_problem(pdir: Path, seeds: int):
    meta = json.loads((pdir / "meta.json").read_text())
    name = meta["name"]
    res = dict(name=name, input_type=meta["input_type"], checker_kind=meta["checker_kind"],
               gen_kind=meta["generator"]["kind"], ok=False, error=None, generators={})
    try:
        BUILD.mkdir(exist_ok=True)
        sol = compile_cached(pdir / "sol.cpp", pdir, "-O2", "sol")
        brute = compile_cached(pdir / "brute.cpp", pdir, "-O2", "brute")
        ver = compile_cached(pdir / "verifier.cpp", pdir, "-O0", "ver")
        chk = compile_cached(pdir / "checker.cpp", pdir, "-O0", "chk")
        gens = sorted((pdir / "gen").glob("generator*.cpp"))
        tmp = BUILD / f"tmp_{name}"
        tmp.mkdir(exist_ok=True)
        for g in gens:
            gb = compile_cached(g, pdir / "gen", "-O0", "gen")
            takes_size = meta["generator"]["takes_size_arg"]
            n_seeds = seeds if g.name == "generator.cpp" else max(20, seeds // 4)
            st = dict(cases=0, mismatch=0, invalid_input=0, timeout=0, crash=0, nondeterministic=0,
                      bytes=[], ms=dict(gen=[], sol=[], brute=[]), first_failure=None)
            for seed in range(n_seeds):
                args = [str(gb), str(seed)] + ([str(SIZES[seed % len(SIZES)])] if takes_size else [])
                inp = tmp / "in.txt"
                try:
                    with open(inp, "wb") as f:
                        r, t = run(args, stdout=f)
                    if r.returncode != 0:
                        st["crash"] += 1
                        continue
                    st["ms"]["gen"].append(t)
                    if seed < 5:   # determinism: same seed twice -> identical bytes
                        r2 = subprocess.run(args, capture_output=True, timeout=TIMEOUT)
                        if r2.stdout != inp.read_bytes():
                            st["nondeterministic"] += 1
                    st["bytes"].append(inp.stat().st_size)
                    v, _ = run([str(ver)], stdin=open(inp, "rb"))
                    if v.returncode != 0:
                        st["invalid_input"] += 1
                        st["first_failure"] = st["first_failure"] or dict(seed=seed, why="verifier rejected input")
                        continue
                    outs = {}
                    for nm, b in (("sol", sol), ("brute", brute)):
                        o = tmp / f"out_{nm}.txt"
                        with open(o, "wb") as f:
                            rr, t = run([str(b)], stdin=open(inp, "rb"), stdout=f)
                        if rr.returncode != 0:
                            st["crash"] += 1
                            st["first_failure"] = st["first_failure"] or dict(seed=seed, why=f"{nm} exited {rr.returncode}")
                            outs = None
                            break
                        st["ms"][nm].append(t)
                        outs[nm] = o
                    if outs is None:
                        continue
                    c, _ = run([str(chk), str(inp), str(outs["sol"]), str(outs["brute"])])
                    st["cases"] += 1
                    if c.returncode != 0:
                        st["mismatch"] += 1
                        st["first_failure"] = st["first_failure"] or dict(seed=seed, why="sol and brute disagree",
                                                                          checker=c.stderr.decode(errors="ignore")[:200])
                except subprocess.TimeoutExpired:
                    st["timeout"] += 1
            b, ms = st["bytes"], st["ms"]
            avg = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
            res["generators"][g.name] = dict(
                cases=st["cases"], mismatch=st["mismatch"], invalid_input=st["invalid_input"],
                timeout=st["timeout"], crash=st["crash"], nondeterministic=st["nondeterministic"],
                bytes_min=min(b) if b else None, bytes_max=max(b) if b else None,
                ms_sol=avg(ms["sol"]), ms_brute=avg(ms["brute"]), first_failure=st["first_failure"])
        res["ok"] = True
    except Exception as e:  # noqa
        res["error"] = str(e)[:600]
    return res


def passed(r):
    return r["ok"] and r["generators"] and all(
        g["cases"] > 0 and g["mismatch"] == g["invalid_input"] == g["timeout"] == g["crash"] == g["nondeterministic"] == 0
        for g in r["generators"].values())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=150)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--budget", type=int, default=10**9, help="stop starting new problems after this many seconds")
    a = ap.parse_args()
    out = ROOT / "tools" / "validation_results.jsonl"
    done = {json.loads(l)["name"] for l in open(out)} if out.exists() else set()
    t_start = time.time()
    for pdir in sorted((ROOT / "problems").glob("*/*")):
        if a.only and pdir.name not in a.only:
            continue
        if pdir.name in done:
            continue
        if time.time() - t_start > a.budget:
            print("budget reached; rerun to continue"); break
        r = validate_problem(pdir, a.seeds)
        with open(out, "a") as f:
            f.write(json.dumps(r) + "\n")
        print(("PASS " if passed(r) else "FAIL "), pdir.parent.name, pdir.name, r["error"] or "", flush=True)
