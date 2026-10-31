# CodeFuzzers v3 roadmap: can sharing the pool help?

## How to work with this roadmap
- Execute ONE step only, and only when the user says "Do Step Vx". Never start the next step on your own.
- After a step: report in the step's OUTPUT format, update the Status table (status + commit hash only), run
  tools/selftest.sh, commit, then STOP and wait.
- If any verification fails: STOP and report the failure. Do not work around it.
- Proposed changes to this roadmap are reported as "Proposed roadmap change" and applied only after the user agrees.

## Status

| Step | Title | Status | Commit |
|---|---|---|---|
| V0 | This roadmap | done | |
| V1 | Hunt test budget + deep bugs (mechanical constants, calibration) | | |
| V2 | trace-cmp value profile | | |
| V3 | Cross-worker splice, origin tracking, pool capacity, v3 arms, 2-slot runner | | |
| V4 | Pre-registered pilot (GO/STOP) | | |
| V5 | Confirmatory (only if V4 = GO) | | |

## Why v3 exists
v1 (hunt-focus) and the v2 tape pilot (STOP, docs/v2_results.md) found no benefit from shared guidance. At K=0,
sharing costs nothing, and it also helps nothing. The causes are listed in docs/v2_roadmap.md "Background":
- the planted bugs are shallow (5–560 generated tests to bug at 8 workers);
- coverage carries no value signal;
- v1 pool entries carry almost no information.

v3 gives sharing a real way to help:
- bugs that need several steps;
- a value signal (trace-cmp value profile);
- an operator that only sharing makes richer (splicing tapes found by other workers).

v3 then tests it with a criterion committed before the data.

## Hypotheses
The primary metric is generated tests-to-bug (tests_before + 1).
- H1 (the sharing claim, confirmatory): on deep bugs, vp-rwlock (one shared pool) reaches the first bug in fewer
  generated tests than vp-noshare (a private pool per worker).
- H2: vp-rwlock vs random-capture. H3: vp-noshare vs random-capture. H2 and H3 form a secondary family.
- Wall time is secondary and descriptive. vp-noshare and vp-rwlock have the same per-test cost, so comparing them in
  tests is fair.

Deep bugs are synthetic, guarded by comparison chains that value profiling is designed to exploit. A positive H1 shows that sharing helps on this bug class; it does not show that sharing helps on typical competitive-programming bugs (off-by-one, overflow, missed edge cases).

## Integrity rules (never break these)
1–7. docs/v2_roadmap.md integrity rules 1–7 apply unchanged:
- the frozen focus set;
- pre-registration documents are append-only;
- v1 results are never modified;
- no extra configurations are run;
- scale behaviour and pool cost are identical to v1;
- the golden generator check.

8. The deep-bug set is fixed by the V1 calibration rule, which uses only the random-capture arm. No v3 guided arm
   runs on a deep bug before docs/v3_pilot_plan.md is committed. Pre-pilot guided runs on deep problems use the CF_NO_PERTURB build only: the guard comparisons are present but no bug can fire and no guard-pass information is recorded, so no tests-to-bug data exists before the pilot plan is committed.
9. Deep-bug constants are set only by the V1 sampling procedure. No constant is chosen by hand.
10. A STOP outcome (V1, the pilot plan's 48 h budget check, or V4) is honoured. v1 and v2 data are never re-analysed to support v3.
11. All v3 results are reported whatever the outcome, in docs/v3_results.md (append-only).

## Seeds (disjoint from every earlier range)
Earlier ranges: v1 1000–1099; pilot 5000–5199; v2 Step 4 20000–20999; Part 2 40000–40005; development 1, 7, 100–102,
999–1019.
- Constant sampling streams: 8000–8009 (unconditional sample) and 8010–8019 (g1-conditional sample).
- Calibration fuzzer seeds: 7000–7019.
- Pilot: 6000–6099.
- Confirmatory: 21000 + r.

## Censoring: by test count, not by wall time
- Every v3 hunt run has a test budget T_max (generated tests) and a wall-time safety cap.
- A run that reaches T_max without a bug is censored:
  - in Mann-Whitney it is tied at the worst rank;
  - in the bootstrap median ratio and in A12 it counts as T_max.
- Why tests: a wall-time cap gives faster arms more tests per censored run, which biases H2/H3 against the slower vp
  arms (trace-cmp overhead).
- A run that hits the wall-time cap is censored exactly like a T_max censoring: tied at the worst rank, counted as
  T_max in the bootstrap and A12, and counted toward the censoring rate. Wall-cap hits are also reported separately
  per cell.
- Why: dropping the slowest runs would be informative censoring and would bias whichever arm hits the cap more
  often. Guard 1 rewards large inputs, so the vp arms may hit the cap more, and not necessarily equally.
- Wall-time cap:
  - calibration (V1): 300 s, because random-capture has no trace-cmp and no size steering;
  - pilot and confirmatory (V4, V5): 3 × (the slowest arm's measured time to T_max in the V3 T4 smoke runs under
    2-slot execution, guard-only CF_NO_PERTURB build), rounded up to a multiple of 60 s, frozen in
    docs/v3_pilot_plan.md.
- Maximum censoring rate (T_max and wall-cap together): 20% per arm × problem cell. Above that, the cell is reported
  but flagged, and it is excluded from the GO and confirmatory decisions.

## Concurrency (V3 smoke, V4, V5; user-approved 2026-10-31)
- Pilot and confirmatory hunt runs execute 2 at a time (2 × 8 workers on the 20 logical CPUs). V5 uses exactly the
  same concurrency as V4, and the pilot plan states it.
- Reason: the primary metric is generated tests-to-bug, and contention does not change its distribution; only
  throughput changes. Scale and other throughput experiments stay solo and are unaffected.
- Solo: V1 throughput measurement and calibration, V2 T2 scale check and T4 overhead.
- V3 T4 smoke runs execute the same set twice, once solo and once 2 at a time. The 2-slot times set the wall-time
  cap, so the cap matches the real conditions. The pair gives the measured 2-slot speedup.
- Expected speedup below 2×: each slot uses 4 cores × 2 hyper-threads, while solo runs use one thread per core
  (CPU_ORDER puts 8 workers on 8 distinct cores). So per-slot throughput is expected to drop, and the speedup
  (serial time / 2-slot wall time) is expected to be below 2×. The planning estimate is 1.4×; V4's ETA uses the
  measured V3 value.
- Slot assignment:
  - both slots take runs from the same randomised block order: slot A runs the even positions (0, 2, ...) of the
    full ordered run list, slot B the odd positions;
  - each slot is an independent sequential queue, and each starts with its own discarded warm-up run (seed 999);
  - each block has 12 runs (3 arms × 4 problems), so each slot gets 6 runs per block, and the shuffle decides which
    arm lands in which slot;
  - the slot is recorded in each run's JSON and in runs.csv.
- Pinning: each slot gets a fixed, symmetric set of 8 logical CPUs, i.e. 4 full vCPU cores with both threads:
  - slot A = CPUs 0–7 (cores 0–3);
  - slot B = CPUs 10–17 (cores 5–8);
  - CPUs 8, 9, 18, 19 (cores 4 and 9) are left for the orchestrator and the OS.
- Topology limit: inside WSL2, lscpu shows 10 identical cores × 2 threads with no P/E information, and Hyper-V maps
  vCPUs to physical P- or E-cores dynamically. Each slot can therefore get the same vCPU mix (4 cores × 2 threads),
  but its physical P/E mix cannot be controlled from inside the VM. Any residual slot difference is balanced across
  arms by the even/odd assignment, and slot is reported as a descriptive covariate. The layout and this limit are
  recorded in docs/v3_pilot_plan.md.

---

## Step V1: Hunt test budget + deep bugs

Scope: core/fuzzer.cpp (hunt test budget only), tools/build.py (build sol_bug_deep), tools/run.py (`--fast bug_deep`),
new tools/deep_calib.py, Dataset/problems/<g>/<p>/sol_bug_deep.cpp, Dataset/bugs_deep.json, CLAUDE.md (Dataset
exception line).

### V1.1 Hunt test budget
- In hunt mode, `--tests N` (N > 0) stops all workers after N generated tests. A run that ends this way without a bug
  is written as censored (`"censored": "tests"`). `--time-limit` stays as the safety cap (`"censored": "time"`).
- A run stopped by the test budget records exactly T_max = N generated tests as its censored value. Tests still in
  flight when the budget is reached (up to 7, one per other worker) are discarded from the metric. A bug found by
  such a test, at generated index > N, does not count: the run is censored at N. The raw generated count is still
  written to the JSON for diagnostics.
- With `--tests 0`, hunt behaviour is unchanged.
- `--fast bug_deep` selects sol_bug_deep. `--fast bug_deep_noperturb` selects its CF_NO_PERTURB build (V1.3).

### V1.2 Throughput and the band in tests
- Measure random-capture throughput R (tests/s, 8 workers, pinned) on the current binaries. Use the first 3 problems
  in manifest order that the calibration will try, 3 runs each with the hunt test budget and fast = sol.cpp (no stop),
  and take the median. This step uses only these 9 runs.
- Band (frozen in V1, recorded in bugs_deep.json): median generated tests-to-bug in
  [B_lo, B_hi] = [round(10 s × R), round(30 s × R)].
- T_max = 3 × B_hi.
- Why tests: tests is the primary metric and does not depend on throughput. V2 adds trace-cmp to the fast binaries
  and slows every arm, so a band in seconds would become wrong after V2. A band in tests does not.
- Why 3×, not 2×: assume tests-to-bug is roughly exponential. Then
  P(censor) = exp(−ln 2 × T_max / median), and a bug at the band's upper edge (median = B_hi) gives:
  - at T_max = 2 × B_hi: exp(−1.386) = 0.25, above the 20% cap;
  - at T_max = 3 × B_hi: exp(−2.079) = 0.125, below it.
- Illustration with R ≈ 8,000 (scale throughput above): band = [80,000, 240,000] tests and T_max = 720,000.

### V1.3 Deep-bug template (fixed here)
- sol_bug_deep.cpp = sol.cpp plus ONE guarded perturbation, placed after the input is read and before the answer is
  printed:
  ```
  if (g1 >= C1) { if (g2 >= C2) { if (g3 % M == C3) { <perturb> } } }
  ```
- g1, g2, g3 are input-level derived values, each computed once per input. They are chosen by this fixed rule and
  written in the file's header comment:
  - g1 = the first count in the input format (size-like: n, q, |S|);
  - g2 = the first element of the first value array (strings: the code of the first string's first character);
  - g3 = the sum over the first value array (strings: the first string's character-code sum).
- Why g2 is the first element, not the maximum: the maximum of a large array is almost surely near the value bound.
  g2 would then be nearly implied by g1 (size), so the real joint rate would be about p × 1/M ≈ p² instead of p³. The
  adjustment rule scales all three guards together, assuming independence, so it could not fix this.
- Each `if` is a separate comparison site, so trace-cmp sees each one.
- `<perturb>`: add 1 to the first integer token of the output. If the output has no integer token, append the token
  `0` to the first output line.
- Note: on problems whose first output token is a count of the items that follow, the +1 can produce a format error
  (the checker sees too few items, or token comparison sees a length mismatch) rather than a wrong value. Both are
  bugs under the outcome rules (WA). T3 records which kind each bug produces.
- Build flag `-DCF_GUARD_LOG` prints `g1 g2 g3` to stderr and exits 0. It is used only by tools/deep_calib.py, never
  in fuzzing builds.
- Build flag `-DCF_FORCE_GUARDS` replaces all three conditions with `true`. It is used only for the V1.5 perturbation
  check.
- Build flag `-DCF_NO_PERTURB` (the guard-only build, binary `fast_bug_deep_noperturb`, selected with
  `--fast bug_deep_noperturb`) keeps the three guard comparisons exactly.
  - The innermost body is replaced by a write to a volatile sink (`volatile int cf_sink; ... cf_sink = 1;`), so the
    comparisons cannot be optimised away.
  - The output is never changed. No guard-pass count or log of any kind is produced.
  - It is used only for pre-pilot guided runs (V3 T3, T4), so the value profile sees the same compare sites as in
    the pilot and steers input sizes the same way, while no bug can fire.
- Nesting note: the guards are nested, so they act as stepping stones in sequence, not in parallel. Value-profile
  distances at the g2/g3 sites are only observed on inputs that already pass the outer guards.

### V1.4 Mechanical constants
- Target pass probability per guard: p = 0.016 (default, fixed here).
- Arithmetic:
  - Band middle = 20 s × R ≈ 160,000 tests (R ≈ 8,000).
  - A median of 160,000 means a per-test rate q = ln 2 / 160,000 = 4.33e-6.
  - p = q^(1/3) = 0.0163, rounded to 0.016.
  - Then p³ = 4.10e-6 and the median is ln 2 / 4.10e-6 ≈ 169,000 tests, near the middle of the band.
- p³ is correct only if the guards pass roughly independently. Independence is checked, not just assumed: the
  conditional check below rejects a g2 that is correlated with g1, and calibration measures the real joint rate.
- Sampling procedure (tools/deep_calib.py):
  - 10 streams s = 0..9, each a `random.Random(8000 + s)` drawing 1,000 recipes the way `random_recipe` does (variant
    uniform, size uniform on 1..max_size, 63-bit generator seed): 10,000 inputs in total.
  - Each input goes through the build/plain/ generator and the `-DCF_GUARD_LOG` build of sol_bug_deep.
- Threshold guards (C1, C2): the constant is the value whose empirical pass rate P(g >= C) is closest to p. Ties go
  to the larger C.
- Equality guard: M = round(1 / p) = 62. C3 is the residue r in 0..M−1 whose empirical rate P(g3 % M == r) is
  closest to p. Ties go to the smaller r.
- If a guard cannot get within a factor of 2 of p (e.g. g1 takes only a few values, or a string alphabet is too
  small for g2), the bug is rejected without calibration ("constant_infeasible").
- Conditional check:
  - Rejection-sample recipes the same way from 10 new streams `random.Random(8010 + s)`, s = 0..9, round-robin,
    until 2,000 inputs pass g1 >= C1. At p = 0.016 that is about 125,000 inputs (250,000 at 0.5p).
  - Report P(g2 >= C2 | g1 >= C1) and P(g3 % M == C3 | g1 >= C1).
  - If P(g2 >= C2 | g1 >= C1) is not within a factor of 2 of p, reject the bug as "constant_correlated" without
    calibration. The g3 conditional rate is reported only.

### V1.5 Perturbation check (before calibration)
- Crafted trigger: one hand-written, verifier-valid input that passes all three guards. sol.cpp and sol_bug_deep must
  disagree on it under the problem's comparison (exact-match or checker).
- 1,000 random inputs: inputs that pass all three real guards occur with probability about p³ = 4e-6. Rejection
  sampling would therefore need about 2.4e8 generator runs, which is not feasible.
- Instead, use the 2,000 g1-passing inputs from the V1.4 conditional check, run the `-DCF_FORCE_GUARDS` build, and
  require the checker (or token comparison) to reject its output on every one. sol.cpp must be accepted on every
  one.
- Any accidental pass (perturbed output accepted) means the perturbation is redesigned before calibration and
  reported.
- Disclosure: this checks the perturbation on inputs that pass guard 1, the size guard, so they have the large sizes
  the real trigger needs. It does not check inputs that pass all three guards. The crafted trigger is the only check
  on an input that passes all three.

### V1.6 Calibration
- Calibration arm: random-capture, not random.
  - Both generate the same per-worker input stream for a given seed. Empty-tape sessions reproduce v1 output by the
    golden test, and neither admits or dedups.
  - They differ only in capture overhead, which shifts the interleaving of the 8 workers. That changes which worker
    finds the first bug in a run, which is expected to leave the distribution of tests-to-bug unchanged.
  - The pilot comparator is random-capture, so calibration uses random-capture to remove any doubt.
- For each candidate: 8 workers, solo (one run at a time), pinned per tools/run.py `CPU_ORDER`, n = 20 runs, seeds
  7000–7019, `--tests T_max`, `--time-limit 300`.
- A bug qualifies if its median generated tests-to-bug (censored = +inf) lies in [B_lo, B_hi] and its censoring rate
  is ≤ 20%.
- Order and cost: write and calibrate one problem at a time, in Dataset/manifest.json order (skip the 3 frozen focus
  problems). Stop as soon as 4 qualify.
- Adjustment (once per bug):
  - if the median is above B_hi or the bug is censored > 20% (too slow), set p ← 2p for all three guards;
  - if the median is below B_lo (too fast), set p ← 0.5p;
  - rebuild C1, C2, M, C3 by the V1.4 procedure (same streams), re-run the V1.5 checks, and calibrate once more;
  - still outside the band: rejected.
- Candidate cap: if 4 bugs have not qualified after 12 candidates (each with at most one adjustment), STOP and report
  (user-approved 2026-10-31). Rejections before calibration (constant_infeasible, constant_correlated) count as
  candidates.
- Rejected bugs stay in Dataset/. Each is listed in bugs_deep.json with `"qualified": false`, its p, constants,
  conditional rates and calibration numbers (median, q1, q3, censored, the reason: constant_infeasible,
  constant_correlated, perturbation, too_slow, too_fast), so the candidate set can be audited.
- Worst-case calibration time: a censored run costs T_max / R = 3 × 30 s = 90 s.
  - One calibration is 20 runs, so at most 30 min. A bug with one adjustment takes at most 60 min.
  - 12 candidates take at most 12 h. Stopping after 4 qualify is expected to need about 4–8 h (4–8 candidates).
- deep_calib sampling cost per bug and round (estimate: about 3 ms per process start from Python, 16 parallel jobs):
  - 10,000 unconditional inputs, plus about 125,000 conditional inputs (250,000 at 0.5p), each run through the
    generator and the CF_GUARD_LOG build, is about 270,000–520,000 process starts;
  - plus 2,000 × 3 (sol, forced build, checker) for the perturbation check;
  - total about 1–2 min, at most 5 min per round with margin;
  - at most 2 rounds per bug gives at most 10 min per bug, so at most 2 h for 12 bugs (expected about 0.5 h).

Tests:
- T1. Golden check + selftest pass.
- T2. Hunt with `--tests 0` reproduces tests_before of 20 v1-style hunt runs (seeds 1000–1019, one hard problem,
  1 worker) exactly.
- T2b. Test budget: with `--tests N` and 8 workers on a problem whose bug is not reachable (fast = sol.cpp), the raw
  generated count (tests_before) lands in [N, N + 7] and the recorded censored value is exactly N (5 runs, N = 10,000).
- T2c. Guard-only build: on each bug's crafted trigger (which passes all three guards), the CF_NO_PERTURB build's
  output is byte-identical to sol.cpp's, while sol_bug_deep's differs (V1.5).
- T3. Per bug: constants table (target p, achieved per-guard rates, P(g2 | g1), P(g3 | g1), status ok /
  constant_infeasible / constant_correlated), crafted trigger result, 2,000-input forced-guard result, and the
  failure kind the perturbation produces (wrong value or format error).
- T4. Calibration table for every candidate tried (qualified or not).

OUTPUT: R, band, T_max; T3 and T4 tables; the 4 qualified problems; commit hash.

---

## Step V2: trace-cmp value profile
Scope: tools/build.py (`COV` for fast binaries), core/fs_runtime.cpp (hooks), core/pool.hpp (map length parameter),
core/fuzzer.cpp (`--value-profile`), CLAUDE.md coverage rule (team-approved).

Requirements (v2 Step 3 spec, reused):
1. Build the fast binaries (sol, sol_bug, sol_bug_deep) with `-fsanitize-coverage=trace-pc,trace-cmp`. Implement
   `__sanitizer_cov_trace_cmp{1,2,4,8}` and `__sanitizer_cov_trace_const_cmp{1,2,4,8}`.
2. Feature = (16-bit hash of PC, bucket of floor(log2(|a − b| + 1))), stored in a separate value-profile map. The
   edge map's semantics are unchanged.
3. `--value-profile`: a child is admitted on a new edge-bucket OR a new value-profile feature. The pool map length
   becomes a constructor parameter (default MAP_SIZE). v1, scale and Entry pools are unchanged.
4. Without the flag, behaviour is unchanged.

Tests:
- T1. Golden check + selftest + `pool_bench --check` pass.
- T2. Scale before/after check (integrity rule 6), as in v2 Step 2c T2.
- T3. Operand log at the three guard sites of one qualified deep bug, on its crafted trigger.
- T4. Overhead: tests/s with vs without trace-cmp on the 4 deep problems. This is a sanity check of the trace-cmp
  cost only; ETAs come from V3 T4.

OUTPUT: diff summary, test results, commit hash.

---

## Step V3: Cross-worker splice, origin tracking, pool capacity, v3 arms
Scope: core/mutate.hpp, core/arena.hpp, core/pool.hpp, core/fuzzer.cpp, tools/run.py (arms, `--slots 2` runner),
tools/flatten.py (slot column), docs/tape_design.md (append a v3 section).

Requirements:
1. Splice operator (`--splice 1`, tape recipes only):
   - child = parent A's tape words up to (not including) the accepted word of A's draw k, then donor B's tape from the
     accepted word of B's draw k;
   - k uniform on [1, min(draws_A, draws_B) − 1], because k = 0 or k = min would just copy one parent;
   - if min(draws) < 2, fall back to a value op;
   - B has the same variant as A and is taken with `pool->pick` (up to 4 retries for a matching variant, then a value
     op);
   - the child keeps A's size and gets a fresh seed;
   - the op actually applied is recorded.
   - Note: splicing aligns tapes by draw index, not by meaning (draw k of A and B may encode different things), so it
     is expected to be weaker than byte-level splicing in AFL/libFuzzer.
2. Operator mix under `--splice 1`: value 40 / nudge 25 / copy 10 / splice 15 / size 10. The v2 `--recipes tape` mix
   (50/25/15/10) is unchanged without the flag.
3. noshare picks B from its own private pool. Both arms splice, and only the donor pool differs, which isolates
   sharing.
4. Origin: `TapeEntry` gains `uint8_t origin` (the admitting worker) in the existing padding;
   static_assert(sizeof(TapeEntry) == 48) stays. Metrics:
   - foreign-parent share of admitted children (parent A, and donor B for splices);
   - origin of A and B for the first bug.

   Chance baseline: with uniform picks and equal contributions from 8 workers, the foreign-parent share in vp-rwlock
   is about 7/8 = 0.875; in vp-noshare it is 0 by construction. vp-rwlock's observed share is reported against 7/8,
   together with the per-run expectation from the pool's final origin mix (1 − Σ_w pick_share_w × pool_share_w). It
   is not reported as a raw percentage.
5. Pool capacity, so both arms hold the same total:
   - today each pool instance holds `MAX_ENTRIES = 4096` (core/pool.hpp:40), so noshare holds 8 × 4096 = 32,768
     entries over 8 workers while rwlock holds 4,096;
   - v3 arms construct the shared pool with capacity 32,768 = 8 × 4096 and each private pool with 4,096;
   - the capacity becomes a constructor parameter with default MAX_ENTRIES, so v1, scale and v2 runs are unchanged.
6. Arena: both arms use the same `--arena-mb`. The V3 smoke runs record peak arena_bytes, and `--arena-mb` is set to
   at least 2× the largest peak (MAP_NORESERVE, so unused space costs nothing). arena_full is reported per run.
7. Arms in tools/run.py `ARMS`:
   - vp-noshare = (noshare, tape, `--value-profile 1 --splice 1`);
   - vp-rwlock = (rwlock, tape, `--value-profile 1 --splice 1`);
   - random-capture unchanged.

   All three use `--fast bug_deep` and `--tests T_max`. The `--time-limit` is the wall-time cap frozen in V4.
8. 2-slot runner (tools/run.py `--slots 2`), per the Concurrency section:
   - even/odd split of the ordered run list;
   - slot A pinned to CPUs 0–7, slot B to CPUs 10–17;
   - one warm-up run per slot;
   - slot recorded per run;
   - resumable as today.

   Without `--slots`, run.py behaves as today (solo).

Tests:
- T1. Golden check + selftest + TSan arena test pass.
- T2. Determinism: 50 admitted entries, including splice children, replay to their stored input hash
  (core/tests/tape_replay_check).
- T3. Operator sanity on one qualified deep problem, with the guard-only build (`--fast bug_deep_noperturb`; no bug
  can fire, integrity rule 8) and `--tests T_max`: 10,000 children, applied fraction per operator, splice fallback rate, mut_changed_input per
  operator.
- T4. Smoke on the 4 qualified problems: one run per v3 arm per problem (seed 1000), with the guard-only build
  (`--fast bug_deep_noperturb`; no bug can fire, integrity rule 8) and `--tests T_max`, so every run goes to T_max.
  The vp arms see the same guard compare sites as in the pilot, so their input sizes and throughput match pilot
  conditions.
  - The same 12-run set runs twice: solo (CPU_ORDER pinning) and with `--slots 2`.
  - Report per arm and problem, for both executions: time to T_max, throughput (tests/s), arena peak, foreign-parent
    share.
  - Report the measured 2-slot speedup = (sum of solo run times) / (2-slot wall time for the whole set).
  - The 2-slot time to T_max of the slowest arm sets the V4 wall-time cap. The per-arm 2-slot throughputs set the V4
    ETA and the fallback decision.
  - Smoke runs are disclosed in the pilot plan.
  - Cost: at most about 1 h (12 runs to T_max, about 90 s for random-capture and about 180 s for a vp arm at overhead
    2, run twice).

OUTPUT: diff summary, test results, commit hash.

---

## Step V4: Pre-registered pilot
Part 1. Write docs/v3_pilot_plan.md, show it to the user, and commit only after confirmation and before any pilot run.
It is append-only after the commit. Contents:
- Problems: the 4 qualified deep problems. Arms: random-capture, vp-noshare, vp-rwlock.
- 8 workers, hunt mode, `--tests T_max`. `--time-limit` = the wall-time cap, 3 × (the slowest arm's V3 T4 time to
  T_max under 2-slot execution with the guard-only build), rounded up to 60 s, with the number written here. n = 100 per arm per problem, seeds 6000–6099,
  randomised blocks (tools/run.py), one discarded warm-up (seed 999).
- Censoring: T_max and wall-cap runs are both censored at the worst rank, per the roadmap's Censoring section.
- Concurrency: 2 runs at a time, slots A/B on CPUs 0–7 and 10–17, even/odd assignment, per the roadmap's Concurrency
  section. The vCPU layout and the WSL2 P/E limitation are recorded here.
- GO criterion: vp-rwlock / vp-noshare median generated tests-to-bug ≤ 0.67 (that is, ≥ 1.5×) on at least 1 problem.
  Cells above 20% censoring are excluded. Otherwise STOP.
- False-GO rate under a no-effect null (4 problems, 1 ratio each, n = 100, exponential and geometric nulls), simulated
  before the commit with tools/fp_sim_v3.py, a copy of tools/fp_sim.py's method with the new threshold and problem
  count. The rate is written into the plan.
- Reporting per problem per arm: median/q1/q3 generated tests-to-bug; censoring rate; wall-cap failures; executed
  tests; wall time; foreign-parent share vs 7/8; arena_full.

Part 2. Run exactly the plan. State GO or STOP using only the committed criterion.

ETA, computed under the null (every arm needs about the calibrated median tests):
- random-capture mean run time, assuming roughly exponential tests-to-bug (mean = median / ln 2):
  - a bug at the band middle (median 20 s) has a mean of 20 / 0.693 ≈ 29 s;
  - a bug at the band's upper edge (median 30 s) has a mean of 30 / 0.693 ≈ 43 s;
  - 35 s is used as a mid-band planning figure (censoring at T_max trims the tail slightly).
- vp arms: until V3 exists, a vp run is assumed to take 2 × 35 s = 70 s (planning overhead factor 2).
- The pilot plan computes each arm's mean run time from its own throughput measured in V3 T4 (guard-only build,
  2-slot) as (planning mean tests) / (measured 2-slot tests/s per run), not from random-capture throughput divided
  by V2's T4 factor. V2 T4 stays as a sanity check of the trace-cmp cost only.
- Serial run time: 100 runs × 4 problems × (35 + 70 + 70) s = 70,000 s ≈ 19.4 h.
- With 2 runs at a time: wall time = serial time / speedup. The planning estimate is 1.4×, giving
  70,000 / 1.4 = 50,000 s ≈ 13.9 h (≈ 9.7 h in the ideal 2× case).
- The pilot plan recomputes the ETA from V3 T4's measured per-arm 2-slot throughputs. Those already include the
  2-slot slowdown, so the result is total 2-slot run time / 2 slots.

OUTPUT: plan commit hash + timestamp, results table, GO/STOP.

---

## Step V5: Confirmatory (only if V4 = GO)
Part 1. Write docs/v3_prereg.md, show it to the user, and commit after confirmation and before any run:
- Scope: all 4 deep problems, even if GO triggered on only one, to avoid winner's-curse selection.
- Arms and settings as in V4, including the same concurrency (2 runs at a time, the same slots and pinning).
  Seeds 21000 + r.
- n: simulated with tools/aggregate.py `power_section` (Mann-Whitney MDE simulation) fed with the pilot's
  per-problem vp-noshare medians, for 80% power at a 1.5× median ratio (one-sided, after Holm over 4). Capped at
  200 per arm per problem.
  - If the cap binds, the prereg states the achieved power per problem.
  - A null result is then reported as "inconclusive at this power", not as "no effect".
- H1 family: 4 per-problem one-sided Mann-Whitney U tests (vp-rwlock < vp-noshare), Holm-corrected. H1 is supported
  if at least 1 problem is significant after Holm in the predicted direction. All 4 are reported regardless.
- H2/H3 family: 8 tests (2 per problem, two-sided), with a separate Holm correction.
- Effect sizes: median ratio with 95% bootstrap CI (2,000 resamples) and A12. Censored runs count as T_max.
- Seeds are shared across arms within a block, but the analysis is unpaired (Mann-Whitney). There is no switch to
  paired tests after the data is seen.
- Cells above 20% censoring are flagged and excluded from the H1/H2/H3 decisions, but reported.
- README is updated after V5 (or after V4 if STOP). It must keep the external-validity caveat from "Hypotheses".

Part 2. Run exactly the plan. Report everything. Run nothing else.

ETA at the cap, under the null with overhead factor 2: 200 × 4 × (35 + 70 + 70) s = 140,000 s ≈ 38.9 h serial. At the
1.4× planning speedup that is 100,000 s ≈ 27.8 h (≈ 19.4 h at 2×).

Pre-approved fallback (user-approved 2026-10-31, decided before any pilot data exists):
- If the worst-case total, recomputed in docs/v3_pilot_plan.md from V1's actual time and V3 T4's measured per-arm
  2-slot throughputs, exceeds 48 h, V5 runs random-capture at n = 100 per problem, while vp-noshare and vp-rwlock stay at n = 200.
- The worst case then uses V1's actual time, the pilot at its worst-case means, and V5 at the cap.
- The H2/H3 power simulation then uses those unequal n (100 vs 200). H1 (vp-rwlock vs vp-noshare) is unaffected.
- The pilot plan states whether the fallback is in force.
- Hard cap (user, 2026-10-31): if the worst case still exceeds 48 h with the fallback, the pilot plan records STOP
  and V4 does not run (see Budget).

OUTPUT: prereg commit hash + timestamp, tables, statistics.

---

## Budget
Assumed vp overhead factor: 2, until V2 T4 measures it.

Planning assumptions, all replaced in the pilot plan by V3 T4's measured per-arm 2-slot throughputs (guard-only
build):
- vp overhead factor 2;
- 2-slot speedup 1.4×;
- V1 runs solo; V4 and V5 run 2 at a time.

| Part | Expected | Worst case |
|---|---|---|
| V1 deep_calib sampling | ~0.5 h | 2 h (12 bugs × 2 rounds × 5 min) |
| V1 calibration (solo) | ~4–8 h (4–8 candidates) | 12 h (12-candidate cap, every bug adjusted once) |
| V3 T4 smoke (solo + 2-slot) | ~1 h | ~1 h |
| V4 pilot (n = 100, 1.4×) | 13.9 h | 13.9 h at the assumed means |
| V5 confirmatory (n = 200 all arms, 1.4×) | 27.8 h | 27.8 h |
| Total at 1.4× | ~47–51 h (≈ 2.0–2.1 days) | ≈ 57 h (≈ 2.4 days) |
| Total in the ideal 2× case (V4 9.7 h, V5 19.4 h) | ~35–39 h | ≈ 44 h |

At 1.4× the worst case is over 48 h, and the expected case is close to it. The pre-approved fallback (V5) handles
this, using measured numbers at pilot-plan time:
- with the fallback, V5 = 4 × (100 × 35 + 2 × 200 × 70) s = 126,000 s serial, so about 25.0 h at 1.4×;
- worst-case total with the fallback ≈ 2 + 12 + 1 + 13.9 + 25.0 ≈ 54 h, still over 48 h;
- expected total with the fallback ≈ 44–48 h.

So even with the fallback, the 2-day budget holds only if V1 needs fewer than the worst-case 12 candidates (expected)
or the measured speedup or overhead turn out better than planned. This is stated here before any data.

Budget decision (user, 2026-10-31): hard cap of 48 h for the whole of v3 (V1 to V5).
- In docs/v3_pilot_plan.md, before any pilot run, the worst-case total is recomputed from V1's actual time, V3 T4's
  measured per-arm 2-slot throughputs, the pilot at n = 100 and V5 at its cap.
- If it exceeds 48 h, the pre-approved fallback is applied (V5 random-capture at n = 100).
- If it still exceeds 48 h with the fallback in force, the pilot plan records STOP and the reason, and V4 does not
  run.
- No other cut (smaller n, fewer problems, shorter T_max) may be applied to fit the cap.

## Proposed CLAUDE.md changes (applied in V1/V2, not in V0)
- "v3 work follows docs/v3_roadmap.md. Read it before any v3 task."
- Dataset exception: sol_bug_deep.cpp per problem and Dataset/bugs_deep.json (user-approved 2026-10-31).
- Coverage rule: fast binaries also carry trace-cmp; value-profile features live in a separate map (V2).
