#!/usr/bin/env python3
"""Reproduces the quoted inline Step S numbers (read-only: existing results and hand-built inputs only) and compares
each with the value documented in docs/shrink_plan.md and docs/v2_results.md. Prints PASS/FAIL per item; exit 1 on any
mismatch (the docs are not changed).
  floors   floor inputs, majority_voting slot-count tests, longest_common_substring predictions, RLARM control
  hand     RLARM hand check on pilot__range_linear_add_range_min__random-capture_w8_k0_f0_r100 (S1 final input)
  headers  S1 header-count table (results/shrink/eval)
  dev      S2 vs S1 on DEV at cap 10,000 (results/shrink/dev_s2, dev_s1_cap10k): smaller / equal / larger
  rightend S2 majority_voting: query right end == n vs < n (results/shrink/eval_s2)
Usage: python3 tools/posthoc_misc.py
"""
import json, os, shutil, sys
from pathlib import Path
import problems, shrink
from aggregate import quant

SH = problems.ROOT / "results" / "shrink"
TMP = Path(f"/dev/shm/cf_posthoc_misc_{os.getpid()}")
fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {got}" + ("" if ok else f"  (documented: {want})"))


def mv(k, l, r):
    return f"{k} 1\n" + " ".join(["0"] * k) + f"\n1 {l} {r}\n"


def floors():
    j = lambda p, t: (shrink.Judge(p, TMP).verdict(t), shrink.ntokens(t), len(t.encode()))
    check("majority_voting floor: 64 copies, [0, 64)", j("majority_voting", mv(64, 0, 64)), ("WA", 69, 140))
    for k, l, r, want in [(63, 0, 63, "ok"), (65, 0, 65, "ok"), (127, 0, 127, "ok"), (128, 0, 128, "WA"), (129, 0, 129, "ok"),
                          (64, 1, 64, "WA"), (64, 0, 63, "ok")]:
        check(f"majority_voting {k} copies, [{l}, {r})", j("majority_voting", mv(k, l, r))[0], want)
    check("range_linear_add_range_min floor", j("range_linear_add_range_min", "1 2\n999999999\n0 0 1 0 2\n1 0 1\n"), ("WA", 11, 30))
    check("range_linear_add_range_min control a + c = 1e9", j("range_linear_add_range_min", "1 2\n999999999\n0 0 1 0 1\n1 0 1\n")[0], "ok")
    check("longest_common_substring floor a / bb", j("longest_common_substring", "a\nbb\n"), ("WA", 3, 5))
    for s, t, want in [("a", "b", "ok"), ("b", "a", "ok"), ("bb", "a", "WA"), ("aa", "b", "ok"), ("b", "aa", "ok")]:
        check(f"longest_common_substring {s} / {t}", j("longest_common_substring", f"{s}\n{t}\n")[0], want)


def hand():
    lines = (SH / "eval" / "pilot__range_linear_add_range_min__random-capture_w8_k0_f0_r100" / "input.txt").read_text().split("\n")[:-1]
    n, q = map(int, lines[0].split())
    judge = shrink.Judge("range_linear_add_range_min", TMP)
    needed = [i + 1 for i in range(q)
              if judge.verdict("\n".join([f"{n} {q - 1}", lines[1]] + [l for j, l in enumerate(lines[2:]) if j != i]) + "\n") != "WA"]
    keep = [lines[2 + i - 1] for i in needed]
    together = "\n".join([f"{n} {len(keep)}", lines[1]] + keep) + "\n"
    check("RLARM hand check: query lines, removable one at a time, needed", (q, q - len(needed), needed), (45, 42, [8, 11, 45]))
    check("RLARM hand check: all removable lines removed together", (judge.verdict(together), shrink.ntokens(together), len(together.encode())),
          ("WA", 30, 231))


def header_rows(d, problem):
    rows = []
    for r in json.loads((d / "summary.json").read_text())["bugs"]:
        if r["problem"] == problem:
            info = json.loads((d / r["bug"] / "info.json").read_text())
            b = Path(info["bug_dir"], "input.txt").read_text().split("\n")[0].split()
            a = (d / r["bug"] / "input.txt").read_text().split("\n")[0].split()
            rows.append((int(b[0]), int(b[1]), int(a[0]), int(a[1])))
    return rows


def headers():
    f3 = lambda v: (round(quant(v, 50), 3), round(quant(v, 25), 3), round(quant(v, 75), 3))
    for p, want in [("range_linear_add_range_min", (941, 61, 627, (0.660, 0.434, 0.851), (1.0, 0.775, 1.0), 43, 15)),
                    ("majority_voting", (967, 0, 721, (0.019, 0.009, 0.052), (1.0, 1.0, 1.0), 1, 103))]:
        h = header_rows(SH / "eval", p)
        got = (len(h), sum(x[1] == x[3] for x in h), sum(x[0] == x[2] for x in h), f3([x[3] / x[1] for x in h]),
               f3([x[2] / x[0] for x in h]), round(quant([x[3] for x in h], 50)), round(quant([x[2] for x in h], 50)))
        check(f"S1 header counts {p} (n, q same, n same, q ratio, n ratio, q after, n after)", got, want)


def dev():
    s2 = {r["bug"]: r["after"]["tokens"] for r in json.loads((SH / "dev_s2" / "summary.json").read_text())["bugs"]}
    s1 = {r["bug"]: r["after"]["tokens"] for r in json.loads((SH / "dev_s1_cap10k" / "summary.json").read_text())["bugs"]}
    check("S2 vs S1 on DEV (smaller, equal, larger)", (sum(s2[b] < s1[b] for b in s2), sum(s2[b] == s1[b] for b in s2),
                                                       sum(s2[b] > s1[b] for b in s2)), (7, 20, 0))


def rightend():
    eq = lt = 0
    for r in json.loads((SH / "eval_s2" / "summary.json").read_text())["bugs"]:
        if r["problem"] == "majority_voting":
            lines = (SH / "eval_s2" / r["bug"] / "input.txt").read_text().split("\n")
            n, q = map(int, lines[0].split())
            t1 = [l.split() for l in lines[2:2 + q] if l.split()[0] == "1"]
            assert len(t1) == 1
            eq, lt = eq + (int(t1[0][2]) == n), lt + (int(t1[0][2]) < n)
    check("S2 majority_voting right end == n / < n", (eq, lt), (965, 2))


def main():
    TMP.mkdir(exist_ok=True)
    try:
        for f in (floors, hand, headers, dev, rightend):
            f()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("ALL REPRODUCE" if not fails else f"{fails} DO NOT REPRODUCE")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
