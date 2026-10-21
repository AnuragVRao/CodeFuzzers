#!/usr/bin/env python3
"""Adds measured bug rates to Dataset/bugs.json and derives "tier" and "kind" from them.
Runs sanity.py --fast sol_bug --seeds 500 --sizes 5,20,max (or parses a saved output via --from).
tier: "hard" if all three rates <= 15 %, else "easy".
kind: small-size if rate5 >= 2*rateMax, large-size if rateMax >= 2*rate5, else structural.
"""
import argparse, json, re, subprocess, sys
from pathlib import Path
import problems

BUGS = problems.DATASET / "bugs.json"


def measure():
    cmd = [sys.executable, str(Path(__file__).parent / "sanity.py"), "--fast", "sol_bug",
           "--seeds", "500", "--sizes", "5,20,max"]
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def parse(text):
    """Rows of the bugs@ table -> {problem: (r5, r20, rmax)}."""
    rates = {}
    for line in text.split("bugs@max", 1)[1].splitlines():
        m = re.match(r"(\S+)\s*\|\s*([\d.]+)%\s*\|\s*([\d.]+)%\s*\|\s*([\d.]+)%", line)
        if m:
            rates[m[1]] = tuple(float(x) for x in m.groups()[1:])
    return rates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", help="saved sanity.py output instead of rerunning")
    a = ap.parse_args()
    rates = parse(Path(a.src).read_text() if a.src else measure())

    bugs = json.loads(BUGS.read_text())
    for b in bugs:
        r5, r20, rmax = rates[b["problem"]]
        b["rate"] = {"5": r5, "20": r20, "max": rmax}
        b["tier"] = "hard" if max(r5, r20, rmax) <= 15 else "easy"
        b["kind"] = "small-size" if r5 >= 2 * rmax else "large-size" if rmax >= 2 * r5 else "structural"
    BUGS.write_text(json.dumps(bugs, indent=2) + "\n")

    for tier in ("hard", "easy"):
        group = [b for b in bugs if b["tier"] == tier]
        print(f"{tier}: {len(group)}")
        for b in group:
            r = b["rate"]
            print(f"  {b['problem']:42} {b['kind']:11} {r['5']:5.1f} {r['20']:5.1f} {r['max']:5.1f}")


if __name__ == "__main__":
    main()
