# Step S2 shrink plan (count-aware reduction; design note)

Frozen in this file's first commit, before any S2 EVAL shrinking; any later change
goes into a dated Amendment section at the end. Same structure as docs/shrink_plan.md (S1, frozen in a4a6aa4); every
section not marked as changed is identical to S1's.

S2 is the final shrinker iteration. No further design changes are evaluated on this EVAL set, whatever S2's results.

## Disclosure
S2 was designed after S1's EVAL results were seen (docs/v2_results.md, "Step S: shrinker evaluation" and "Step S:
post-hoc diagnosis"), including a hand-check on one EVAL input (pilot__range_linear_add_range_min__random-capture_w8_k0_f0_r100),
in which 42 of 45 query lines could be removed once the header count was decremented. S2 was then built and tuned on
DEV only. S1's EVAL results are reported unchanged alongside S2's.

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


## (b) Stages (CHANGED: stage 2 is new; deterministic order, predicate checked at every accepted step)
0. Tape capture: as S1.
1. Tape shrink: as S1 (stages 1a-1d).
2. NEW count-aware reduction (tools/shrink.py, stage "3" in info.json), on the smallest input after stage 1, repeated
   until a full pass accepts nothing:
   2a. delete k consecutive lines after the first line, k = the largest power of two <= the number of such lines,
       halving to 1, left to right;
   2b. then, for each line after the first, delete k consecutive tokens of that line (k halving from the largest power
       of two <= its token count to 1), left to right.
   Every deletion is tried with the first line unchanged, then with each integer token of the first line decremented by
   k, in that order (a non-negative token is never decremented below 0). Generic: no per-problem grammar; the verifier
   and the full predicate (a) decide. Every accepted candidate removes at least one token (strict progress); every
   candidate goes through the per-candidate budget check.
   DEV evidence for "headers on the first line": every DEV format with counts has them on the first line (n q / N M /
   N; deque_operate_all_composite's first line counts its query lines); the string problems have no integer header.
3. Text ddmin: as S1 stage 2 (line-level, then token-level within lines), on the stage-2 result.
4. Result: the smallest predicate-satisfying input seen (tokens, then bytes, then earliest).
info.json records the input size (tokens, bytes) at every stage boundary (stage_sizes: start, after_tape,
after_count, after_ddmin, or at_stop on a budget stop) and shrinker "s2". `--s1` runs S1 unchanged (verified: S1's
DEV outputs reproduced byte-for-byte, info.json identical except wall_s).

## (c) Budget (per input; unchanged from S1)
- At most 10,000 evaluations and a 300 s wall stop (safety net only); every EVAL input hitting the wall stop is listed
  by name and flagged.
- DEV data gives no reason to change them: S2 on the 27 DEV bugs used at most 8,262 evaluations (median 178), with no
  cap and no wall-stop hits. On DEV (S1 re-run at the same cap), S2's after-tokens were smaller than S1's for 7 bugs,
  equal for 20 and larger for none; every S2 improvement over S1 came from the count stage; in number_of_substrings,
  suffixarray and zalgorithm, ddmin removed further tokens after it (S1 = S2 there).
- All stages share one 10,000-evaluation budget, spent in stage order (the tape stage first). The report lists every
  cap hit with the stage in which the budget ran out (from stage_sizes: no after_tape mark = tape stage; after_tape but
  no after_count = count stage; after_count but no after_ddmin = ddmin stage). Stage order and budget are as S1's
  plus the count stage; they are not changed.

## Run (CHANGED: S2 only; once, no re-runs)
- On an otherwise idle machine: `python3 tools/shrink_run.py --set eval --shrinker new --jobs 8 --max-evals 10000
  --wall 300 --out results/shrink/eval_s2`, then `python3 tools/shrink_run.py --set eval --replay --out
  results/shrink/eval_s2`.
- S1 and the old shrinker are not re-run: their EVAL results (results/shrink/eval/, results/shrink/eval_old/, reported
  in docs/v2_results.md at fda85cf) are reported unchanged alongside S2's.
- results/raw/ and results/bugs/ are checked against the sha256 snapshot before and after.

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


## (e) Metrics (CHANGED: S2, S1 and the old shrinker side by side on the same EVAL set)
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

- S2 additionally reports the median size at each stage boundary (after tape, after count-aware, after ddmin) and
  S2 vs S1 after-tokens per distinct input (smaller / equal / larger).

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


## EVAL-size rule (unchanged rule; applied to S2)
Projected S2 cost = 4.08 ms (median per-evaluation cost of S2 on DEV, 8 parallel) x 10,000 x 1,973 distinct inputs / 8
= about 2.8 hours worst case (every input at the cap), within 8 hours: the full EVAL set is used.

## Known limitation: the well-formedness proxy
For exact-match problems "well-formed" means the same number of whitespace-separated tokens as ref's output. This
misclassifies problems whose correct output length varies with the answer: in DEV, lyndon_factorization's bug prints
9 tokens against ref's 6, so its original verdict is PE and it is not shrunk. It does not apply to the focus problems:
- majority_voting prints exactly one token per t = 1 query (the value or -1), so the token count is fixed by the input;
- range_linear_add_range_min prints exactly one integer per t = 1 query;
- longest_common_substring is judged by its checker (exit 1 = WA), not by token counts; its output is always 4 integers.


## Known limitation: no index renumbering
S2 decrements first-line headers but never rewrites indices inside body lines, so n cannot fall below the largest index
any surviving line refers to. For range_linear_add_range_min this predicts final inputs above the 11-token floor (a
needed query or update that refers to index i keeps at least i values). Index renumbering is out of scope (future
work); the final-iteration rule stands.

## Reporting note
"Success" (the final input satisfies the predicate) is near-tautological: both shrinkers accept only
predicate-satisfying candidates and keep the original otherwise. The primary metrics are the reduction ratio
(after / before), the gap to the floor (after / floor), and the fraction of inputs exactly at the floor.


## (f) Tests (CHANGED: S2 tests added)
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

- nc3: decrementing a header count without deleting the matching body line is rejected by the verifier.
- S2 unit test: on a synthetic range_linear_add_range_min-shaped input (20 queries, 1 needed; stub with the verifier's
  count rules) stage 2 reduces it to the needed query with q = 1 (and n = 4, the minimum reachable without editing indices inside
  query lines, not the true minimum).
- `--s1` reproduces S1's DEV outputs byte-for-byte (input.txt; info.json except wall_s).
- The S1 negative controls (nc1, nc2), the hang regression and determinism pass under S2.

## (g) Output (CHANGED)
results/shrink/eval_s2/<bug id>/ (input.txt, info.json with stage_sizes) and summary.json, representatives.json.
Nothing under results/raw/ or results/bugs/ changes (sha256 snapshot before and after).

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
