#!/usr/bin/env python3
"""Tests of the Step S shrinker (tools/shrink.py, docs/shrink_plan.md), on DEV (non-focus gallery) bugs only.
  nc1  an N/count-mismatch candidate on which ref and sol_bug both exit 0 and disagree is rejected (verifier)
  nc2  a candidate whose verdict changes from WA to PE / unexpected EOF is rejected (a sol_bug wrapper that drops
       the last output line; exact-match problem -> PE, custom checker -> PE or EOF)
  det  two shrinker runs on the same bugs give byte-identical inputs and info (wall time excluded)
Usage: python3 tools/shrink_test.py [--quick]   (--quick: smaller determinism budget, for the selftest)
"""
import argparse, json, os, shutil, stat, subprocess, sys
from pathlib import Path
import problems, shrink

BUGS = problems.ROOT / "results" / "bugs"
EXACT_DEV, CUSTOM_DEV = "range_add_range_min", "two_edge_connected_components"  # its checker gives PE on a truncated output


def nc1(tmp):
    """First DEV bug (sorted) and count change (+1, -1 on the first token) where ref and sol_bug disagree."""
    judge = None
    for d in sorted(p for p in BUGS.iterdir() if p.is_dir()):
        if problems.get(d.name)["checker_kind"] == "custom" or d.name in ("majority_voting", "range_linear_add_range_min"):
            continue
        text = (d / "input.txt").read_text()
        head, rest = text.split(None, 1)[0], text[len(text.split(None, 1)[0]):]
        if not head.isdigit():
            continue
        judge = shrink.Judge(d.name, tmp)
        for delta in (1, -1):
            cand = str(int(head) + delta) + rest
            judge.inp.write_text(cand)
            if problems._run([judge.ref], judge.inp, judge.ans, None, "") != 0 or problems._run([judge.fast], judge.inp, judge.out, None, "") != 0:
                continue
            if judge.out.read_bytes().split() == judge.ans.read_bytes().split():
                continue
            v = judge.verdict(cand)
            return d.name, delta, v, v != "WA" and v == "invalid"
    return None, None, None, False


def nc2(problem, tmp):
    bins = problems.plain_bins(problems.get(problem), "sol_bug")
    wrapper = tmp / "drop_last_line.sh"
    wrapper.write_text(f'#!/bin/sh\n"{bins["sol_bug"]}" | head -n -1\n')
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    text = (BUGS / problem / "input.txt").read_text()
    real = shrink.Judge(problem, tmp).verdict(text)
    fake = shrink.Judge(problem, tmp, fast=wrapper).verdict(text)
    return real, fake


def det(budget, tmp):
    picks = ["range_add_range_min", "zalgorithm"]
    runs = []
    for k in range(2):
        out = tmp / f"det{k}"
        infos = [shrink.shrink_bug(p, BUGS / p, out / p, budget, 600.0) for p in picks]
        runs.append([((out / p / "input.txt").read_bytes(), {x: y for x, y in i.items() if x != "wall_s"}) for p, i in zip(picks, infos)])
    return picks, runs[0] == runs[1], [i["evals"] for _, i in runs[0]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    tmp = Path(f"/dev/shm/cf_shrink_test_{os.getpid()}")
    tmp.mkdir(exist_ok=True)
    fails = 0
    try:
        prob, delta, v, ok = nc1(tmp)
        print(f"{'PASS' if ok else 'FAIL'}  nc1 count mismatch: {prob}, first token {delta:+d}: ref and sol_bug exit 0 and "
              f"disagree; verdict {v} -> rejected" if prob else "FAIL  nc1: no count-mismatch candidate found")
        fails += not ok
        for problem in (EXACT_DEV, CUSTOM_DEV):
            real, fake = nc2(problem, tmp)
            ok = real == "WA" and fake in ("PE", "EOF")
            print(f"{'PASS' if ok else 'FAIL'}  nc2 {problem}: original verdict {real}; sol_bug minus its last line -> {fake} (rejected)")
            fails += not ok
        picks, same, evals = det(100 if a.quick else 600, tmp)
        print(f"{'PASS' if same else 'FAIL'}  det: two runs on {picks} (evals {evals}) give byte-identical inputs and info")
        fails += not same
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ALL PASS" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
