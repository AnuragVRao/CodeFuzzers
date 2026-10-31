#!/usr/bin/env python3
"""Cold-start replay of every final shrunk input (read-only): one predicate evaluation (tools/shrink.py Judge, fresh
processes) per final input, which must give the original verdict.
  old  results/shrink/eval_old/<bug id>/bug/shrunk/input.txt  (1,973 distinct EVAL inputs; original verdict WA)
  S1   results/shrink/eval/<bug id>/input.txt                 (EVAL; WA)
  S2   results/shrink/eval_s2/<bug id>/input.txt              (EVAL; WA)
  S2 DEV results/shrink/dev_s2/<bug id>/input.txt             (27 DEV bugs; info.json original_verdict)
Usage: python3 tools/shrink_replay_check.py [--jobs 8]   prints matched / total per set and every mismatch; exit 1 on any
"""
import argparse, json, os, shutil, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import problems, shrink

SH = problems.ROOT / "results" / "shrink"


def judge(job):
    problem, path, want = job
    tmp = Path(f"/dev/shm/cf_replay_check_{os.getpid()}")
    tmp.mkdir(exist_ok=True)
    return str(path), want, shrink.Judge(problem, tmp).verdict(Path(path).read_text())


def jobs():
    sets = {}
    for name, d, final in (("old", SH / "eval_old", lambda b: SH / "eval_old" / b / "bug" / "shrunk" / "input.txt"),
                           ("S1", SH / "eval", lambda b: SH / "eval" / b / "input.txt"),
                           ("S2", SH / "eval_s2", lambda b: SH / "eval_s2" / b / "input.txt")):
        rows = json.loads((d / "summary.json").read_text())["bugs"]
        sets[name] = [(r["problem"], final(r["bug"]), "WA") for r in rows]
    dev = json.loads((SH / "dev_s2" / "summary.json").read_text())["bugs"]
    sets["S2 DEV"] = [(r["problem"], SH / "dev_s2" / r["bug"] / "input.txt", r["original_verdict"]) for r in dev]
    return sets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    bad = 0
    with ProcessPoolExecutor(a.jobs) as ex:
        for name, js in jobs().items():
            res = list(ex.map(judge, js, chunksize=16))
            miss = [(p, w, v) for p, w, v in res if v != w]
            bad += len(miss)
            print(f"{name:7} {len(res) - len(miss):5} / {len(res):5} final inputs reproduce the original verdict")
            for m in miss:
                print("   mismatch (input, expected, got):", m)
    for d in Path("/dev/shm").glob("cf_replay_check_*"):
        shutil.rmtree(d, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
