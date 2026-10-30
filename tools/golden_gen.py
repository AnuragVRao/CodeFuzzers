#!/usr/bin/env python3
"""Golden generator test: sha256 of stdout of every fuzzer generator binary (build/<problem>/gen and
gen_alt) for seeds {1, 2, 3, 12345, 987654321} x sizes {1, 5, 50, 200}, stored in
core/tests/golden_gen.json under "<problem>/<binary>/<seed>/<size>". A non-zero exit is part of the
value ("<sha256> rc=<n>"), so a generator that starts or stops skipping a seed is also a mismatch.

Usage: python3 tools/golden_gen.py           record (overwrites the golden file)
       python3 tools/golden_gen.py --check   recompute, print every mismatch, exit 1 on any
Run tools/build.py (--force after header changes) first.
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


def digest(key):
    name, binary, seed, size = key.split("/")
    exe = problems.ROOT / "build" / name / binary
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
    bad = [k for k in sorted(want.keys() | got.keys()) if want.get(k) != got.get(k)]
    for k in bad:
        print(f"MISMATCH {k}: golden={want.get(k)} now={got.get(k)}")
    print(f"{len(want) - len(bad)}/{len(want)} entries match" + (f", {len(bad)} mismatches" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
