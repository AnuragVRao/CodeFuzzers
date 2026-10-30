#!/usr/bin/env python3
"""Exploratory, post-hoc analysis of the Step 2e pilot (results/raw/pilot/, read-only). NOT part of any verdict.
(a) Bug-finding test of every tape-arm run: ROOT (no parent: empty input tape, recipe.txt tape_words 0) or CHILD
    (input tape = a mutated copy of a parent's tape, never empty). The CHILD's operators are not recoverable: the
    pilot ran without --op-log and the parent of a bug is not recorded.
(b) Per tape-arm run: fraction of generated tests that were roots = (generated - mutated) / generated. mutated counts
    children whose generator ran OK; the pilot had no gen_skip and no budget exit, so it counts every child. These are
    whole-run counts: they include tests still in flight when the bug stopped the run (up to 7 with 8 workers).
(c) 95% percentile bootstrap CI of each tape / random-capture median generated tests-to-bug ratio:
    tools/aggregate.py ratio_ci() (2,000 resamples of each group), seed SEED for every comparison.
(d) Rate decomposition (model-based): lambda_fresh = ln2 / median generated tests-to-bug of random-capture,
    lambda_tape = ln2 / median of the tape arm, r = median root fraction (b); predicted root-found share
    = r * lambda_fresh / lambda_tape (next to the observed share from (a)); relative child productivity
    = (lambda_tape - r * lambda_fresh) / ((1 - r) * lambda_fresh).
Usage: python3 tools/pilot_posthoc.py   (prints markdown)
"""
import json, math, statistics
import problems
from aggregate import quant, ratio_ci

RAW = problems.ROOT / "results" / "raw" / "pilot"
PROBLEMS = ["majority_voting", "range_linear_add_range_min", "longest_common_substring"]
TAPE_ARMS = ["tape-noshare", "tape-rwlock"]
SEED = 20261030


def runs(p, a):
    for r in range(200):
        d = json.loads((RAW / p / f"{a}_w8_k0_f0_r{r}.json").read_text())
        recipe = dict(l.split(None, 1) for l in (RAW / p / f"{a}_w8_k0_f0_r{r}" / "recipe.txt").read_text().splitlines()) \
            if d["first_bug"] else {}
        yield r, d, recipe


def main():
    print("Post-hoc, descriptive; not part of any verdict. Source: results/raw/pilot (Step 2e Part 3).\n")
    print("(a) Bug-finding test: ROOT (empty input tape) vs CHILD. Operators of CHILD bugs: not recoverable (no --op-log in")
    print("the pilot; parents of bugs are not recorded).\n")
    print("| problem | arm | runs with a bug | ROOT-found | CHILD-found |")
    print("|---|---|---:|---:|---:|")
    observed, root_frac, medians = {}, {}, {}
    for p in PROBLEMS:
        for a in TAPE_ARMS:
            words = [int(rec["tape_words"]) for _, d, rec in runs(p, a) if d["first_bug"]]
            observed[(p, a)] = sum(w == 0 for w in words) / len(words)
            print(f"| {p} | {a} | {len(words)} | {sum(w == 0 for w in words)} | {sum(w > 0 for w in words)} |")

    print("\n(b) Fraction of generated tests that were roots, per run ((generated - mutated) / generated, whole run).\n")
    print("| problem | arm | median fraction of roots | q1 | q3 |")
    print("|---|---|---:|---:|---:|")
    for p in PROBLEMS:
        for a in TAPE_ARMS:
            fr = [(d["generated"] - d["mutated"]) / d["generated"] for _, d, _ in runs(p, a)]
            root_frac[(p, a)] = statistics.median(fr)
            print(f"| {p} | {a} | {statistics.median(fr):.3f} | {quant(fr, 25):.3f} | {quant(fr, 75):.3f} |")

    print(f"\n(c) Median generated tests-to-bug ratio tape / random-capture with a 95% percentile bootstrap CI "
          f"(2,000 resamples, seed {SEED}); post-hoc, descriptive.\n")
    print("| problem | arm | ratio | 95% CI |")
    print("|---|---|---:|---|")
    for p in PROBLEMS:
        base = [d["first_bug"]["tests_before"] + 1 if d["first_bug"] else float("inf") for _, d, _ in runs(p, "random-capture")]
        medians[(p, "random-capture")] = quant(base, 50)
        for a in TAPE_ARMS:
            tape = [d["first_bug"]["tests_before"] + 1 if d["first_bug"] else float("inf") for _, d, _ in runs(p, a)]
            medians[(p, a)] = quant(tape, 50)
            lo, hi = ratio_ci(base, tape, SEED)
            print(f"| {p} | {a} | {quant(tape, 50) / quant(base, 50):.3f} | [{lo:.3f}, {hi:.3f}] |")

    print("\n(d) Rate decomposition: post-hoc, model-based, descriptive. Assumptions: constant per-test bug rates;")
    print("approximately exponential tests-to-bug (so rate = ln2 / median); roots find the bug like random-capture tests")
    print("(rate lambda_fresh); root fractions r are whole-run medians from (b) (up to 7 in-flight tests included).\n")
    print("| problem | arm | lambda_fresh | lambda_tape | r | predicted root-found share | observed root-found share "
          "| relative child productivity |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for p in PROBLEMS:
        lf = math.log(2) / medians[(p, "random-capture")]
        for a in TAPE_ARMS:
            lt, r = math.log(2) / medians[(p, a)], root_frac[(p, a)]
            print(f"| {p} | {a} | {lf:.5f} | {lt:.5f} | {r:.3f} | {r * lf / lt:.3f} | {observed[(p, a)]:.3f} "
                  f"| {(lt - r * lf) / ((1 - r) * lf):.3f} |")


if __name__ == "__main__":
    main()
