#!/usr/bin/env python3
"""Golden generator test: sha256 of stdout of every fuzzer generator binary (build/<problem>/gen and
gen_alt) for seeds {1, 2, 3, 12345, 987654321} x sizes {1, 5, 50, 200}, stored in
core/tests/golden_gen.json under "<problem>/<binary>/<seed>/<size>". A non-zero exit is part of the
value ("<sha256> rc=<n>"), so a generator that starts or stops skipping a seed is also a mismatch.
--check compares two flavours against the same hashes: the runtime-linked binaries (fs_runtime.o,
cf_session defined) and the build/plain/ generators (no runtime, cf_session weak and absent).

Usage: python3 tools/golden_gen.py           record from the runtime-linked binaries (overwrites the file)
       python3 tools/golden_gen.py --check   recompute both flavours, print every mismatch, exit 1 on any
Run tools/build.py first (build/plain/ generators are compiled here if out of date).
"""
import argparse, hashlib, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import problems

GOLDEN = problems.ROOT / "core" / "tests" / "golden_gen.json"
SEEDS, SIZES = (1, 2, 3, 12345, 987654321), (1, 5, 50, 200)
BINARIES = {"generator": "gen", "generator_alt_1": "gen_alt"}


def jobs():
    for p in problems.load():
        for v in p["variants"]:
            for seed in SEEDS:
                for size in SIZES:
                    yield f"{p['name']}/{BINARIES[v]}/{seed}/{size}"


def exe_path(key, plain):
    name, binary = key.split("/")[:2]
    if not plain:
        return problems.ROOT / "build" / name / binary
    p = problems.get(name)
    v = {b: v for v, b in BINARIES.items()}[binary]
    return problems.compile(p["dir"] / "gen" / f"{v}.cpp", problems.PLAIN / name / v, problems.flags(p["dir"]))


def digest(key, plain=False):
    name, binary, seed, size = key.split("/")
    exe = exe_path(key, plain)
    r = subprocess.run([str(exe), seed, size], capture_output=True, timeout=30)
    h = hashlib.sha256(r.stdout).hexdigest()
    return key, h if r.returncode == 0 else f"{h} rc={r.returncode}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="compare against the golden file instead of writing it")
    a = ap.parse_args()
    with ThreadPoolExecutor() as ex:
        got = dict(ex.map(digest, jobs()))
    if not a.check:
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
        print(f"recorded {len(got)} entries -> {GOLDEN.relative_to(problems.ROOT)}")
        return 0
    want = json.loads(GOLDEN.read_text())
    keys = sorted(want)
    for p in problems.load():  # compile build/plain/ generators once, before the parallel runs
        for v in p["variants"]:
            exe_path(f"{p['name']}/{BINARIES[v]}", True)
    with ThreadPoolExecutor() as ex:
        plain = dict(zip(keys, (h for _, h in ex.map(lambda k: digest(k, True), keys))))
    failed = 0
    for flavour, now in (("runtime-linked", got), ("build/plain", plain)):
        bad = [k for k in sorted(want.keys() | now.keys()) if want.get(k) != now.get(k)]
        for k in bad:
            print(f"MISMATCH {flavour} {k}: golden={want.get(k)} now={now.get(k)}")
        print(f"{flavour}: {len(want) - len(bad)}/{len(want)} entries match" + (f", {len(bad)} mismatches" if bad else ""))
        failed |= bool(bad)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
