# Step S shrink plan (design note, Phase 0)

Frozen in this file's first commit, before any EVAL shrinking; any later change goes into a dated Amendment
section at the end. Built and tested on DEV in commit 19d9c71 (tools/shrink.py, tools/shrink_run.py,
tools/shrink_test.py, core/tape_file_runtime.cpp).

## (a) Bug-preserving predicate
A candidate input preserves the bug only if its verdict EQUALS the original's, judged from fresh processes (the
plain path of tools/problems.py, not the fork-server):
1. the problem's verifier (build/<problem>/verifier, testlib registerValidation) accepts it (exit 0);
2. ref (brute.cpp) exits 0 within the timeout;
3. fast = sol_bug exits 0 within the timeout;
4. verdict WA: for longest_common_substring the checker exits exactly 1 (testlib _wa); for the exact-match problems
   the output is well-formed (the same number of whitespace-separated tokens as ref's output) and some token
   differs. Every original EVAL bug must have this verdict (checked at stage 0).
PE (2), dirt (4), unexpected EOF (8), ref_fail (3), checker_error, a token-count mismatch, TLE and crash do NOT count.
Reason: sol_bug.cpp is the correct sol.cpp plus one planted line, so a WA on verifier-valid input that both programs
process normally implies the planted bug; other verdicts could come from malformed or degenerate inputs instead.

All three focus problems have a usable verifier:
- majority_voting: N and Q in range, exactly N values, Q query lines whose indices are bounded by N, EOF.
- range_linear_add_range_min: n and q in range, exactly n values, q lines with l < r <= n and bounded b, c, EOF.
- longest_common_substring: two lines of one token each, 1 <= length <= N_MAX, lowercase letters only (it accepts
  letters other than a/b, which the generator never emits), EOF.

## (b) Stages (deterministic order, predicate checked at every accepted step)
0. Tape capture (section "Tape source" below): obtain the bug's full consumed tape and draw log, regenerate the
   input, and require its sha256 to equal the saved input.txt; otherwise the bug is reported as "capture mismatch"
   and not shrunk.
1. Tape shrink (build/tape/ generator, fallback_zero on, budget 1,000,000 words; a budget exit rejects the
   candidate). Passes, repeated until a full pass accepts nothing:
   1a. truncate: binary search on tape length (the tail then reads 0);
   1b. delete spans of words, lengths 8, 4, 2, 1, left to right;
   1c. set each draw's accepted word to 0, left to right;
   1d. reduce each remaining non-zero draw value by binary search toward 0, left to right.
   A candidate is accepted only if the generated input satisfies the full predicate (a). Among accepted candidates
   the pass keeps the first one found (fixed order), so the result is deterministic.
2. Text ddmin on the Phase 1 input: line-level ddmin, then token-level ddmin within each line (tokens as for
   mut_similarity: -?\d+ runs or single non-whitespace characters, so a longest_common_substring string is reduced
   character by character). Every candidate is checked with the full predicate (a).
3. Result: the smallest predicate-satisfying input seen (tokens first, then bytes; ties: earliest found).

## (c) Budget (per input)
- At most 10,000 evaluations (stages 1 and 2 together; memoised candidates cost nothing) and a 300 s wall stop.
- The evaluation cap is the deterministic budget; the 300 s wall stop is a safety net only (10,000 x the largest
  per-evaluation cost measured on DEV, 11.82 ms, is about 118 s). An input that hits either keeps its best input so
  far and is counted under "hit budget (evaluations)" or "hit budget (wall)"; every EVAL input that hits the wall
  stop is listed by name and flagged, since its result depends on timing. Determinism claims apply to runs that hit
  no wall stop.
- Chosen from DEV data: at a cap of 2,000, 3 of 27 DEV bugs hit the cap; uncapped they needed 2,101, 3,071 and
  8,232 evaluations.

## Run (once, no re-runs)
- The two shrinkers run one after the other on the same machine, which is otherwise idle: first the new shrinker,
  `python3 tools/shrink_run.py --set eval --shrinker new --jobs 8 --max-evals 10000 --wall 300`
  (8 inputs in parallel, as when the per-evaluation cost was measured), then the old shrinker,
  `python3 tools/shrink_run.py --set eval --shrinker old --jobs 16` (one input at a time, 16-worker pool), then the
  cold-start replay `python3 tools/shrink_run.py --set eval --replay --out results/shrink/eval`.
- results/raw/ and results/bugs/ are checked against the snapshot of every file's sha256 before and after.

## (d) Bug sets
- DEV (building and tuning): the 27 non-focus gallery bugs in results/bugs/ (all WA), plus bugs found on non-focus
  problems with development seeds only (1, 7, 999-1019). No focus-problem bug is ever used for development.
- EVAL (frozen here, no cherry-picking): every focus-problem bug from
  - the v2 pilot: results/raw/pilot/*/ (3 problems x 3 arms x 200 = 1,800 bugs);
  - v1: results/raw/hunt/ focus problems (810 bug dirs) and results/raw/hunt-focus/ (900 bug dirs);
  - the 3 focus bugs of the v1 gallery (results/bugs/{majority_voting, range_linear_add_range_min,
    longest_common_substring}).
  Total 3,513 bugs. Identical inputs (same problem, same input sha256) are shrunk once; metrics are reported both
  per bug (with multiplicity) and per distinct input. A bug whose tape capture fails the hash check stays in the
  denominator as a failure ("capture mismatch").

## (e) Metrics (new shrinker AND old shrinker on the same EVAL set)
- Unit: per distinct input (same problem, same input sha256) is primary; per bug (with multiplicity) is secondary.
- "Before" for BOTH shrinkers = the saved input.txt (tokens and bytes), for every EVAL bug including tape children.
- Old shrinker (tools/shrink.py --old, code unchanged) on every EVAL bug: started on a copy of the bug directory
  (input.txt and recipe.txt copied under results/shrink/; never in place). It uses only the recipe's variant and size
  plus input.txt as its starting best, so tape children are handled the same way as roots (their tape is ignored;
  its candidates are fresh-seed v1 recipes). Seed per bug = int(sha256(bug id)[:8], 16), recorded in the output.
- success rate: final input satisfies predicate (a);
- size before/after in tokens (median, IQR) and bytes (median, IQR);
- predicate evaluations per bug; wall time per bug (median, IQR);
- failure breakdown: capture mismatch / produced invalid input / lost the bug / hit budget (evaluations, wall) /
  crash / other.
The old shrinker is run on copies of the bug directories under the new results folder: tools/shrink.py writes into
<bug-dir>/shrunk/, which must not happen under results/raw/.

## Yardstick: smallest triggering input per focus bug (derived from Dataset/bugs.json and sol_bug.cpp; verified)
Shrunk sizes are reported relative to these floors (tokens as for mut_similarity; bytes include newlines). Each floor
input was run through the predicate (hand-built inputs only, no EVAL input) before this plan was frozen.
- majority_voting: 69 tokens, 140 bytes; `64 1`, 64 zeros (A_MIN = 0), `1 0 64` -> WA (ref 0, sol_bug -1).
  FenwickTree::add loops `while (i < n)` (sol_bug.cpp:79), so the last node (n = m blocks of 64 slots) is never
  updated, and only sum() at block m reads it: the bug needs a query whose right end reaches past all slots of a
  value whose slot count is an exact multiple of 64. Verified: 64 and 128 copies (full query) and 64 copies queried
  over [1, 64) trigger; 63, 65, 127 and 129 copies and 64 copies queried over [0, 63) do not. Slots are distinct
  positions < N, so N >= 64, plus one query. Dataset/bugs.json's trigger ("more than 64 occurrence slots") is
  therefore inaccurate (proposed correction reported separately; bugs.json unchanged). Confidence: high.
- range_linear_add_range_min: 11 tokens, 30 bytes; `1 2` / `999999999` / `0 0 1 0 2` / `1 0 1` -> WA (ref
  1000000001, sol_bug 1000000000). query() starts its minimum at 1e9 (sol_bug.cpp:116), so a queried range whose
  values all exceed 1e9 returns 1e9; values start <= A_MAX = 1e9, so one linear add (index i gets a_i + i*b + c) and
  one query are needed. A 9-digit a_i plus a 1-digit c is the fewest digits above 1e9. Control: a_i + c = 1e9 exactly
  does not trigger. Confidence: high.
- longest_common_substring: 3 tokens (characters), 5 bytes; `a` / `bb` -> WA (sol_bug 0 0 1 1; also `bb` / `a` ->
  1 1 0 0). `ans` starts at -1 (sol_bug.cpp:141), so with no common character the first adjacent (s-suffix,
  t-suffix) pair in suffix-array order sets a length-0 answer at that pair's positions, which the checker rejects
  unless it starts at 0. The suffix-array prediction (empty suffix first) matched all 6 no-common-character inputs of
  up to 3 characters: `a`/`b`, `b`/`a`, `aa`/`b`, `b`/`aa` do not trigger. Confidence: high.

## EVAL-size rule (decided before any EVAL shrinking)
Projected cost = measured per-evaluation cost on DEV x evaluation cap x distinct EVAL inputs, for the new shrinker,
plus the old shrinker's measured per-bug cost on DEV x distinct EVAL inputs, divided by the cores used. If <= 8 hours,
use the full EVAL set. Otherwise use a seeded, stratified random sample: 100 distinct inputs per focus problem,
allocated to the populations (v1 hunt, v1 hunt-focus, v1 gallery, pilot random-capture, pilot tape-noshare, pilot
tape-rwlock) in proportion to their distinct-input counts (largest remainder), drawn with random.Random(20261031).

## Known limitation: the well-formedness proxy
For exact-match problems "well-formed" means the same number of whitespace-separated tokens as ref's output. This
misclassifies problems whose correct output length varies with the answer: in DEV, lyndon_factorization's bug prints
9 tokens against ref's 6, so its original verdict is PE and it is not shrunk. It does not apply to the focus problems:
- majority_voting prints exactly one token per t = 1 query (the value or -1), so the token count is fixed by the input;
- range_linear_add_range_min prints exactly one integer per t = 1 query;
- longest_common_substring is judged by its checker (exit 1 = WA), not by token counts; its output is always 4 integers.

## Reporting note
"Success" (the final input satisfies the predicate) is near-tautological: both shrinkers accept only
predicate-satisfying candidates and keep the original otherwise. The primary metrics are the reduction ratio
(after / before), the gap to the floor (after / floor), and the fraction of inputs exactly at the floor.

## (f) Tests
- f1 negative control: from a DEV bug, build an input with a count mismatch (first line's N one larger than the
  number of values that follow) for which ref and sol_bug still disagree; the predicate must reject it (verifier),
  and the shrinker must never accept it. Also check ref_fail / checker_error / TLE / crash candidates are rejected.
- f2 cold-start replay: every final shrunk input re-checked from fresh processes (verifier, ref, sol_bug,
  checker) reproduces the WA.
- regression for the fixed stage-1 hang (re-padded trailing deletions under fallback_zero): the tape stage on a
  re-padding stub terminates within 64 evaluations (tools/shrink_test.py; the pre-fix logic does not terminate).
- f3 determinism: two runs on the same bugs give byte-identical shrunk inputs and logs.
- f4 tape capture: for a DEV bug of each population, the captured tape regenerates input.txt exactly.
- f5 golden check + selftest pass.

## (g) Output
results/shrink/eval/<bug id>/ (new shrinker: input.txt, info.json) and results/shrink/eval_old/<bug id>/ (old
shrinker: the copied bug directory and its shrunk/), each with summary.json; <bug id> names the population, problem
and run (e.g. pilot__majority_voting__tape-rwlock_w8_k0_f0_r17). Identical inputs are shrunk once per distinct input
(the representative is the first bug in the fixed order of tools/shrink_run.py; representatives.json maps every bug
to it, for the per-bug metrics). Nothing under results/raw/ or results/bugs/ changes; this is
checked before and after against a snapshot of every file's sha256 (including docs/v2_pilot_raw.sha256).

## Tape source per bug population
- v1 first bugs and the v1 gallery: no tape was recorded. Capture: run the build/tape/ generator of the recipe's
  variant with an empty input tape and the recipe's seed and size; with no input words, random.h's tape_next()
  returns this instance's xoshiro words (Dataset/common/random.h, line 47), i.e. exactly v1's draws.
- Pilot random-capture bugs: no tape.bin (record_bug() saves a tape only for --recipes tape, core/fuzzer.cpp line
  341); the generator ran in an empty tape session (core/fuzzer.cpp lines 195, 269), so the same capture as v1
  applies.
- Pilot tape-arm bugs: tape.bin is the generator's INPUT tape (core/fuzzer.cpp lines 137, 152-153): empty for a
  root, the mutated copy of the parent's tape for a child. Capture: run with tape.bin as the input tape plus the
  recipe's seed and size (words past the end of tape.bin come from that seed's xoshiro); the output tape of that
  run is the full consumed sequence that stage 1 shrinks.
- In every case the regenerated input must hash to the saved input.txt before shrinking (stage 0).
