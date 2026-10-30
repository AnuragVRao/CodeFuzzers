#!/usr/bin/env python3
"""The C++ (core/compare.hpp checker_outcome, through the fork-server) and Python (problems.run_checker)
checker classifiers must agree on exit codes 0, 1, 2, 3, 4, 5, 7, 8, 16, 255, a signal and a timeout.
C++ results are parsed from build/tests/checker_test; Python runs the same test binaries
(build/tests/exit_code <n>, crash, hang). Prints one line per case; exit 1 on any disagreement.
Usage: python3 tools/checker_agree_test.py   (after tools/build.py)
"""
import re, subprocess, sys
import problems

TESTS = problems.ROOT / "build" / "tests"
CASES = {f"exit {n}": ([str(TESTS / "exit_code"), str(n)], 2) for n in (0, 1, 2, 3, 4, 5, 7, 8, 16, 255)}
CASES["killed by SIGABRT"] = ([str(TESTS / "crash")], 2)
CASES["timeout (SIGALRM)"] = ([str(TESTS / "hang")], 0.2)


def main():
    r = subprocess.run([str(TESTS / "checker_test")], cwd=problems.ROOT, capture_output=True, text=True)
    cpp = {m[1]: m[2] for m in re.finditer(r"^(?:PASS|FAIL)  (.+?)\s+-> (\S+)", r.stdout, re.M)}
    bad = 0
    if set(cpp) != set(CASES):
        print(f"FAIL  case lists differ: C++ {sorted(cpp)} vs Python {sorted(CASES)}")
        bad += 1
    for name, (cmd, timeout) in CASES.items():
        py = problems.run_checker(cmd, timeout)
        ok = cpp.get(name) == py
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name:20} C++ {cpp.get(name)!s:14} Python {py}")
    print("ALL AGREE" if not bad else f"{bad} DISAGREEMENTS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
