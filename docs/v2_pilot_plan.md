# v2 pilot plan (Step 2e)

Pre-registration for the exploratory v2 pilot. Append-only once committed: any later change goes into a dated
"Amendment" section at the end of this file and is reported. Nothing in this plan is run before its commit.

## Purpose
Decide whether to proceed to the v2 confirmatory study (Step 4). The pilot is exploratory only.

## Build
- Every arm, including the comparator, and Part 2 run on the build of commit 99e05aa
  ("Part 2: mut_similarity over changed children; truncation guard"), which contains the pilot tooling of 6aadf8e.
- Runs execute from this plan's own commit, which differs from 99e05aa only in docs/ and CLAUDE.md (commit 9d41762
  and this plan's commit; `git diff --stat 99e05aa..HEAD -- core/ Dataset/ tools/` is empty). Part 3 run JSONs record
  that later hash (git_commit, stamped by tools/run.py); Part 2's outputs record no commit, so its report states it.
- Any later code change that touches the fuzzer (core/), the generators (Dataset/), or the tools (tools/) before the
  pilot completes goes into a dated Amendment section here, stating what changed and why.
- Commands: Part 2 = `python3 tools/part2.py` (defaults: the 6 Part 2 problems, seed base 40000, 2,000 warm-up
  tests, 2,000 children per mode, output results/part2/); Part 3 = `python3 tools/run.py --exp pilot --preset full`.

## Design
- Problems: the 3 frozen focus problems: majority_voting, range_linear_add_range_min, longest_common_substring.
- Arms: random-capture (comparator: random strategy + --tape-capture, v2 build), tape-noshare, tape-rwlock.
  tape-rwlock-span is not part of the decision.
- 8 workers, hunt mode, fast = sol_bug, time limit 20 s per run; a run without a bug within 20 s is censored and
  counts as +inf tests-to-bug.
- n = 200 runs per arm per problem; seeds 5000 + r, r = 0..199 (5000-5199).
- Randomised blocks as in tools/run.py: repeat r is one block containing every arm x problem configuration (9 runs),
  shuffled with block seed 5000 + r, which is recorded as "block_seed" in each run's JSON; one discarded warm-up run
  first, with development seed 999.

## Part 2 (mutation diagnostics; runs before Part 3)
- Problems: the 3 focus problems plus the first non-focus problem alphabetically in each group: deque_operate_all_composite
  (arrays), enumerate_palindromes (strings), cartesian_tree (graphs).
- Seeds: 40000 + i for the i-th problem in the order majority_voting, range_linear_add_range_min,
  longest_common_substring, deque_operate_all_composite, enumerate_palindromes, cartesian_tree (40000-40005).
- Parents (the same parent source for all three modes): one warm-up run of the fuzzer per problem, arm tape-rwlock
  with 1 worker (deterministic), scale mode with the correct solution, 2,000 warm-up tests, --seed = the problem's
  Part 2 seed. Every entry admitted during the warm-up is a parent; build/part2 regenerates each parent from its
  stored tape and checks that the output hash equals the stored one.
- Children: 2,000 per mode per problem. Child i's parent is a uniform draw (with replacement) from a parent stream
  seeded with the problem's seed, so the three modes use the same parent sequence; the child is made by a mutation
  stream seeded seed x 1000003 + mode index (guided 0, byte 1, draw 2):
  - v1 guided: the parent's variant, size x v1 size factor, fresh seed, plain generator run;
  - tape byte (--tape-mut byte): the parent's tape with one random byte of one random word replaced, fresh seed;
  - tape draw-level: the parent's tape with 1..8 draw-level operators (docs/tape_design.md), fresh seed.
  Tape children run in a tape session with the 1,000,000-word budget. No ref/fast runs, no pool, no admission.
- Saved per problem (results/part2/<problem>/): parents and children with both generator outputs, and every child's
  applied operators in --op-log format (draw ops: draw index, old and new value; size: old size, new size, factor).
- Metrics per problem per mode, over children whose generator run was OK: mut_changed_input = children whose output
  hash differs from the parent's / OK children; mut_similarity =
  difflib.SequenceMatcher(None, parent_tokens, child_tokens, autojunk=False).ratio(), where a token is a maximal run
  of digits with an optional leading '-', otherwise any single non-whitespace character (whitespace only separates
  tokens), first 20,000 tokens of each output (as in docs/tape_design.md).
- Denominator: criterion (a)'s "median mut_similarity" (and its IQR) is the median over the children whose input
  changed (mut_changed = 1) only. The median over all OK children (an unchanged child counting 1.0) is reported as
  descriptive only.
- Truncation: the 20,000-token cap never triggers for the Part 2 set. Static maxima from the generator code at size
  200 (every Part 2 size is <= max_size = 200): majority_voting 802, range_linear_add_range_min (gen and gen_alt)
  1,202, longest_common_substring 400, deque_operate_all_composite 1,001, enumerate_palindromes 200, cartesian_tree
  201 tokens. tools/part2.py aborts if any parent or child output would be truncated.
- Diagnostics from the operator log (single-op change rates, same-value writes, size no-op routes) are descriptive
  only and are NOT part of the kill criterion.

## Kill criterion (verbatim from docs/v2_roadmap.md, Step 2e, at commit 99e05aa; unchanged since 5e06271)
> - Kill criterion: PROCEED only if (a) for draw-level tape mutation, measured in Part 2 (2,000 children per problem): mut_changed_input >= 0.80 AND median mut_similarity >= 0.50, on all 3 focus problems, AND (b) at least one problem has median generated tests-to-bug (tests_before + 1) for tape-noshare or tape-rwlock <= 0.70x random-capture. Otherwise STOP tape work.
> - Metric note: tests-to-bug means generated tests-to-bug (tests_before + 1, v1's definition) throughout Steps 2e and 4. Reason: random-capture does not dedup, so executed tests-to-bug excludes the tape arms' dup-skips but counts random's duplicates. Decided before any pilot data (Q3 of the Step 2d review).

Application rules:
- Medians are over the 200 runs of one arm x problem, with censored runs as +inf.
- If more than half of an arm x problem's runs are censored, its median is undefined, and any comparison that uses
  it (as tape arm or as random-capture comparator) cannot satisfy (b).
- (a) uses only the Part 2 measurement; (b) uses only the Part 3 runs.

## Reporting
- Per problem per arm: median/p25/p75 generated tests-to-bug (primary); executed tests-to-bug median/p25/p75
  (secondary, descriptive); median wall_s; generated vs executed; dup_skip; gen_budget_exceeded; tape_overflow.
- arena_full and tape_overflow are reported per run; every run with arena_full > 0 is listed by name.
- Known caveat: the tape arena is one per process, so the private per-worker pools of tape-noshare share one arena;
  if a tape-noshare run fills it, admission stops for all its workers at once (a coupling between otherwise private
  pools). The behaviour on a full arena is the same in every tape arm: the child is not admitted, the run continues.
- PROCEED or STOP is stated using only this committed criterion.

## Confirmatory seeds (proposal for Step 4)
Step 4 uses seeds 20000 + r, r = 0..999 (20000-20999). This range is disjoint from this pilot (5000-5199), from
Part 2 (40000-40005), from v1 (1000-1099), and from every fuzzer --seed used in v2 development (1, 7, 100-102,
999-1019; 999 is also the pilot's discarded warm-up). The pilot and Part 2 ranges are disjoint from each other and
from all of these too.

## Disclosures
- Before this criterion was committed, Step 2d's T4 smoke runs (n = 1 per arm per problem, seed 1000) showed
  mut_changed_input of 0.818-0.838 for longest_common_substring in the tape-rwlock and tape-rwlock-span arms
  (0.897 for tape-noshare). Those are hunt runs with whole-run mut_changed_input, not the Part 2 measurement that
  criterion (a) uses. The 0.80 threshold was not changed after seeing them.
- The size operator has a built-in no-op rate of at least 1/3: two of its six factor slots are 1 (v1 parity), plus
  clamping to [1, max_size] and growth within the same power-of-two mask band (the replayed tape then yields the
  same values). It was deliberately left unchanged after the Step 2d T3/T4 data was seen; operator weights and size
  factors are as specified in docs/tape_design.md.
- The tokenisation for mut_similarity was fixed before any Part 2 data, after noticing that whitespace tokenisation
  treats each string in longest_common_substring as one token (one changed character -> ratio 0.5, on the
  threshold), and that difflib's default autojunk discards frequent tokens, which majority_voting's inputs contain
  by design.
- The denominator of median mut_similarity (changed children only) was fixed before any Part 2 data; including
  unchanged children (similarity 1.0) would let no-op mutations inflate the median.
- False-PROCEED rate of (b) alone, under a no-effect null (all 9 arm x problem groups drawing tests-to-bug from the
  same distribution; "any of the 6 tape/random median ratios <= 0.70"; tools/fp_sim.py, 200,000 replicates):
  at the originally planned n = 50 it is about 45% (0.447 exponential, 0.446 geometric), which is why n was raised
  before any pilot data; at n = 200 it is about 3.8% (0.0378 exponential, 0.0372 geometric; per comparison 0.0067).
  A PROCEED licenses only the confirmatory study, which has its own Holm family.
