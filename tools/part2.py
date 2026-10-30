#!/usr/bin/env python3
"""Step 2e Part 2: mutation diagnostics (docs/v2_pilot_plan.md, docs/tape_design.md). Per problem:
1. Parents: one warm-up run of build/fuzzer, arm tape-rwlock with 1 worker (deterministic), scale mode with the
   correct solution, WARMUP tests, seed = seed_base + index of the problem; every entry it admits (--dump-tapes)
   is a parent.
2. Children: build/part2 draws CHILDREN children per mode (guided = v1 guided, byte = tape --tape-mut byte,
   draw = tape draw-level) from that parent set, with one parent sequence shared by the three modes; it saves
   the (parent, child) pairs, both generator outputs and the --op-log operator list.
3. Offline: per mode, over children whose generator run was OK: mut_changed_input = changed / OK, and
   mut_similarity = similarity(parent output, child output) (median, q1, q3).
similarity: tokens = maximal runs of digits with an optional leading '-', otherwise any single non-whitespace
character (whitespace only separates tokens), first 20,000 tokens of each output;
ratio = difflib.SequenceMatcher(None, parent_tokens, child_tokens, autojunk=False).ratio().
Usage: python3 tools/part2.py [--problems P ...] [--seed-base 40000] [--warmup 2000] [--children 2000]
                              [--out results/part2] [--check-only]
       python3 tools/part2.py --selftest      (similarity unit tests)
--check-only: run the pipeline and print PASS/FAIL structure checks only, never metric values (smoke tests).
"""
import argparse, difflib, json, re, statistics, subprocess, sys
from pathlib import Path
import problems
from run import FOCUS_PROBLEMS

ROOT = problems.ROOT
MODES = ["guided", "byte", "draw"]
TOKEN = re.compile(r"-?\d+|\S")
MAX_TOKENS = 20000


def part2_problems():
    """The 3 focus problems + the first non-focus problem alphabetically in arrays, strings, graphs."""
    names = [p for p in FOCUS_PROBLEMS]
    for g in ("arrays", "strings", "graphs"):
        names.append(sorted(p["name"] for p in problems.load() if p["group"] == g and p["name"] not in FOCUS_PROBLEMS)[0])
    return names


def tokens(text):
    return TOKEN.findall(text)[:MAX_TOKENS]


def similarity(a, b):
    return difflib.SequenceMatcher(None, tokens(a), tokens(b), autojunk=False).ratio()


def read_framed(path):
    """{index: text} from a file of "index bytes\\n" + raw bytes records (core/part2.cpp)."""
    data, out, pos = Path(path).read_bytes(), {}, 0
    while pos < len(data):
        nl = data.index(b"\n", pos)
        i, n = map(int, data[pos:nl].split())
        out[i] = data[nl + 1:nl + 1 + n].decode()
        pos = nl + 1 + n
    return out


def read_tsv(path):
    lines = Path(path).read_text().splitlines()[1:]
    return [dict(i=int(f[0]), parent=int(f[1]), status=int(f[5]), changed=f[8]) for f in (l.split() for l in lines)]


def produce(name, seed, warmup, children, d):
    """Steps 1 and 2 for one problem into directory d."""
    p, cfg = problems.get(name), problems.max_sizes()[name]
    build, variants = ROOT / "build" / name, len(p["variants"])
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(ROOT / "build/fuzzer"), "--build", str(build), "--variants", str(variants), "--max-size", str(cfg["max_size"]),
                    "--checker", "custom" if p["checker_kind"] == "custom" else "exact", "--mode", "scale", "--fast", "sol",
                    "--strategy", "rwlock", "--recipes", "tape", "--workers", "1", "--tests", str(warmup), "--seed", str(seed),
                    "--out", str(d / "warmup.json"), "--bug-dir", str(d / "warmup_bug"), "--dump-tapes", str(d / "parents.txt")],
                   check=True, capture_output=True)
    subprocess.run([str(ROOT / "build/part2"), "--build", str(build), "--variants", str(variants), "--max-size", str(cfg["max_size"]),
                    "--parents", str(d / "parents.txt"), "--modes", ",".join(MODES), "--children", str(children),
                    "--seed", str(seed), "--out", str(d)], check=True, capture_output=True)


def measure(d):
    """Step 3: per mode {children, ok, mut_changed_input, mut_similarity_median/q1/q3}, plus the raw similarities."""
    parents = read_framed(d / "parents.out")
    out = {}
    for m in MODES:
        rows, texts = read_tsv(d / f"{m}.tsv"), read_framed(d / f"{m}.out")
        ok = [r for r in rows if r["status"] == 0]
        sims = [similarity(parents[r["parent"]], texts[r["i"]]) for r in ok]
        q = statistics.quantiles(sims, n=4) if len(sims) > 1 else [None] * 3
        out[m] = dict(children=len(rows), ok=len(ok), mut_changed_input=sum(r["changed"] == "1" for r in ok) / len(ok) if ok else None,
                      mut_similarity_median=statistics.median(sims) if sims else None, mut_similarity_q1=q[0], mut_similarity_q3=q[2],
                      _sims=sims, _rows=rows, _texts=texts)
    return out


def check(name, d, children, res):
    """Structure checks for --check-only (no metric values printed)."""
    parents = (d / "parents.txt").read_text().splitlines()
    seqs = [[r["parent"] for r in res[m]["_rows"]] for m in MODES]
    checks = [("parents admitted by the warm-up and all reproduced by build/part2", len(parents) > 0 and len(read_framed(d / "parents.out")) == len(parents)),
              (f"{children} children per mode", all(res[m]["children"] == children for m in MODES)),
              ("same parent sequence in every mode", seqs[0] == seqs[1] == seqs[2]),
              ("one saved output per OK child", all(set(res[m]["_texts"]) == {r["i"] for r in res[m]["_rows"] if r["status"] == 0} for m in MODES)),
              ("every child has at least one logged operator", all(all(l.split()[10] != "0" for l in (d / f"{m}.tsv").read_text().splitlines()[1:]) for m in MODES)),
              ("every similarity is a number in [0, 1]", all(all(0 <= s <= 1 for s in res[m]["_sims"]) and len(res[m]["_sims"]) == res[m]["ok"] for m in MODES))]
    for what, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {what}")
    return all(ok for _, ok in checks)


def selftest():
    """Unit tests of similarity() on hand-written pairs."""
    ten = " ".join(map(str, range(1, 11)))
    rep = " ".join(str((i * 37 % 11) % 2) for i in range(400))  # repeated values: 400 tokens, all 0 or 1
    flip = " ".join(t if i != 200 else str(1 - int(t)) for i, t in enumerate(rep.split()))  # token 200 flipped
    cases = [
        ("identical", similarity("3 4\n1 -2 3\n", "3 4\n1 -2 3\n"), lambda r: r == 1.0),
        ("one number changed in a 10-number list", similarity(ten, ten.replace("7", "70")), lambda r: r == 0.9),
        ("one character changed in a 2-string input", similarity("abcde\nfghij\n", "abcde\nfghiX\n"), lambda r: r == 0.9),
        ("  (whitespace tokens would give exactly 0.5)", difflib.SequenceMatcher(None, "abcde fghij".split(), "abcde fghiX".split()).ratio(), lambda r: r == 0.5),
        ("repeated-value list (400 tokens of 0/1, one flipped)", similarity(rep, flip), lambda r: r > 0.99),
        ("  (difflib's default autojunk would give, far below)", difflib.SequenceMatcher(None, tokens(rep), tokens(flip)).ratio(), lambda r: r < 0.9),
        ("tokens: '-12 x3' -> ['-12', 'x', '3']", tokens("-12 x3") == ["-12", "x", "3"], lambda r: r),
    ]
    bad = 0
    for what, r, ok in cases:
        bad += not ok(r)
        print(f"{'PASS' if ok(r) else 'FAIL'}  {what}: {r}")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", nargs="+", default=None, help="default: the 6 Part 2 problems")
    ap.add_argument("--seed-base", type=int, default=40000, help="seed of problem i = seed_base + i")
    ap.add_argument("--warmup", type=int, default=2000)
    ap.add_argument("--children", type=int, default=2000)
    ap.add_argument("--out", default=str(ROOT / "results" / "part2"))
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    names, ok, summary = a.problems or part2_problems(), True, {}
    for i, name in enumerate(names):
        d = Path(a.out) / name
        produce(name, a.seed_base + i, a.warmup, a.children, d)
        res = measure(d)
        if a.check_only:
            ok &= check(name, d, a.children, res)
        else:
            summary[name] = dict(seed=a.seed_base + i, **{m: {k: v for k, v in r.items() if not k.startswith("_")} for m, r in res.items()})
    if a.check_only:
        print("ALL PASS" if ok else "SOME CHECKS FAILED")
        return 0 if ok else 1
    (Path(a.out) / "summary.json").write_text(json.dumps(dict(warmup=a.warmup, children=a.children, problems=summary), indent=1) + "\n")
    print(f"wrote {Path(a.out) / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
