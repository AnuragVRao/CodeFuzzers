# CodeFuzzers v3 roadmap (short): can sharing the pool help?

Replaces the long v3 plan of commit 3ff4493, which is kept in git history. Target: about 10 h in total, coding
included. Only the parts that give sharing a mechanism to help are kept: deep bugs, a value signal, and a
cross-worker operator. Everything else (pilot/confirmatory split, test-count censoring, 2-slot runner, conditional
and forced-guard checks, secondary hypotheses) is cut.

## How to work with this roadmap
- One step per prompt ("Do Step Vx"), in order. After a step: run tools/selftest.sh, commit, report, STOP.
- If a verification fails: STOP and report. Do not work around it.
- docs/v2_roadmap.md integrity rules 1–7 still apply (frozen focus set, append-only pre-registrations, v1 results
  untouched, no extra configurations, scale behaviour unchanged, golden generator check).
- This document is the pre-registration for V4. The design section below is frozen when V3 is committed. Changes
  after that go in a dated "Amendment" section at the end.

## Status

| Step | Title | Est. | Status | Commit |
|---|---|---|---|---|
| V1 | Deep bugs on 3 problems | 2.5 h | done | 39e9f40 |
| V2 | trace-cmp value profile | 2 h | done | 59755dd |
| V3 | Cross-worker splice, origin, equal pool capacity, arms | 2 h | done (design frozen) | |
| V4 | The experiment (one pre-registered run set) | 2 h | | |
| V5 | Report + README | 1 h | | |

## Why
v1 and v2 found no benefit from sharing the pool. There are three reasons:
- the bugs are found in 5–560 tests, so the pool has hardly filled by then;
- coverage carries no value signal;
- a pool entry carries little information.

v3 fixes exactly these three things and nothing else:
- deeper bugs, guarded by a chain of comparisons;
- trace-cmp value profiling, which rewards getting closer to a guard;
- a splice operator that takes the donor from the pool, so with sharing the donor can come from another worker.

## Hypothesis (the only confirmatory one)
- H1: on the deep bugs, vp-rwlock (one shared pool) needs fewer generated tests to the first bug than vp-noshare
  (a private pool per worker). Both arms have the same per-test cost, so tests is a fair basis.
- random-capture is run as a descriptive reference only, not tested.
- Caveat (keep in the README): deep bugs are synthetic, guarded by comparison chains that value profiling is designed
  to exploit. A positive H1 shows that sharing helps on this bug class, not on typical competitive-programming bugs.
- Power: with n = 100 per arm, the existing Mann-Whitney simulation (tools/aggregate.py, two-sided, alpha 0.05,
  80% power) gives a minimum detectable median ratio of about 1.6×; the one-sided test with Holm over 3 problems is
  somewhat worse. A null result is reported as "no effect of ~1.6× or more detected", not as "no effect".

---

## Step V1: Deep bugs on 3 problems (2.5 h)
Scope: Dataset/problems/<g>/<p>/sol_bug_deep.cpp, Dataset/bugs_deep.json, tools/build.py, tools/run.py
(`--fast bug_deep`), new tools/deep_calib.py, CLAUDE.md (Dataset exception line).

- Template: sol_bug_deep.cpp = sol.cpp plus one guarded perturbation, after the input is read:
  ```
  if (g1 >= C1) { if (g2 >= C2) { if (g3 % M == C3) { <add 1 to the first integer token of the output> } } }
  ```
  - g1 = the first count in the input (n, q, |S|);
  - g2 = the first element of the first value array (strings: the first character's code);
  - g3 = the sum of that array (strings: the character-code sum).
  - Each `if` is a separate comparison, so trace-cmp sees each one.
  - `-DCF_GUARD_LOG` prints `g1 g2 g3` and exits; it is used only by tools/deep_calib.py.
- Constants are mechanical, never hand-picked:
  - target per-guard pass rate p = 0.026, so p³ ≈ 1.76e-5 and the median is ln 2 / p³ ≈ 39,000 tests (about 5 s
    for random-capture at ≈ 8,000 tests/s, 8 workers);
  - sample 2,000 inputs (random sizes and seeds, `random.Random(8000)`, the way `random_recipe` draws them) and run
    them through the generator and the CF_GUARD_LOG build;
  - C1, C2 = the constants whose empirical pass rate is closest to p;
  - M = round(1/p) = 38, and C3 = the residue whose rate is closest to p.
- Check: one hand-written trigger input that passes all three guards; sol.cpp and sol_bug_deep must disagree on it.
- Calibration (random-capture only, 8 workers, 10 runs, seeds 7000–7009, 60 s limit):
  - a bug qualifies if its median tests-to-bug is in [15,000, 120,000] (deep, but found within the limit);
  - if it misses, adjust once: p ← 2p if too slow, p ← p/2 if too fast; rebuild the constants and calibrate again;
  - candidates in Dataset/manifest.json order, skipping the 3 frozen focus problems; take the first 3 that qualify;
  - STOP if 3 have not qualified after 6 candidates.
  - Every candidate tried, qualified or not, is listed in bugs_deep.json with its constants and calibration numbers.
- Rule: no guided arm runs on a deep bug before V3 is committed.

OUTPUT: constants and calibration table, the 3 problems, commit hash.

## Step V2: trace-cmp value profile (2 h)
Scope: tools/build.py (fast binaries only), core/fs_runtime.cpp, core/pool.hpp, core/fuzzer.cpp.

- Fast binaries get `-fsanitize-coverage=trace-pc,trace-cmp`. Implement the `__sanitizer_cov_trace_cmp{1,2,4,8}` and
  `__sanitizer_cov_trace_const_cmp{1,2,4,8}` hooks.
- Feature = (16-bit PC hash, bucket of floor(log2(|a − b| + 1))), kept in a separate value-profile map. The edge
  map is unchanged.
- `--value-profile 1`: a child is admitted on a new edge-bucket OR a new value-profile feature. The pool's map length
  becomes a constructor parameter (default MAP_SIZE), so v1 and scale pools are unchanged.
- Tests:
  - selftest (including golden and `pool_bench --check`);
  - the operand log at the three guard sites on one trigger input;
  - tests/s with vs without trace-cmp on the 3 deep problems.
- As built (deviation, recorded 2026-10-31): only fast_bug_deep (and, from V3, fast_bug_deep_noperturb) carry
  trace-cmp; fast_sol and fast_bug are unchanged, so the v1/v2 and scale binaries stay identical. Measured cost of
  `--value-profile 1` vs trace-pc only: 0.92–0.93× tests/s (8 workers, random strategy).
- Leftover check (done before V3): the compare sites firing on a trigger input, grouped by function, included the
  stdout capture/rewrite helpers of core/deep_bug.hpp (24 of 65 sites on range_add_range_min). The helpers are now
  `no_sanitize_coverage` (and use no std::string); afterwards only the solution's own code fires (37 sites).
  vp_features (random strategy, 40,000 tests, seed 1010) before → after: 519 → 486, 256 → 226, 453 → 400.

OUTPUT: diff summary, overhead table, commit hash.

## Step V3: Cross-worker splice, origin, equal pool capacity, arms (2 h)
Scope: core/mutate.hpp, core/arena.hpp, core/pool.hpp, core/fuzzer.cpp, tools/run.py.

- Splice (`--splice 1`):
  - child = parent A's tape words for draws 0..k−1 (up to and including the accepted word of A's draw k−1), then
    donor B's words from just after the accepted word of B's draw k−1 (as built in core/mutate.hpp);
  - k is uniform on [1, min(draws) − 1]; if min(draws) < 2, it falls back to a value op;
  - a splice ends the child's operator list (A's draw log no longer describes the tape after it);
  - B has the same variant as A and is taken with `pool->pick` (4 retries, then a value op).
  - Operator mix with the flag: value 40 / nudge 25 / copy 10 / splice 15 / size 10. Without the flag the v2 mix is
    unchanged.
  - noshare picks B from its own pool, so only the donor pool differs between the arms. This isolates sharing.
- Origin: `TapeEntry` gets `uint8_t origin` in its existing padding (still 48 bytes).
  - Metric: the foreign-parent share of admitted children.
  - Chance baseline in vp-rwlock: about 7/8; in vp-noshare it is 0 by construction.
  - This is the direct evidence that the shared arm actually builds on other workers' finds.
- Equal capacity: the shared pool holds 8 × 4096 = 32,768 entries, the same total as 8 private pools of
  `MAX_ENTRIES = 4096` (core/pool.hpp). The capacity is a constructor parameter, default unchanged.
- Arms in tools/run.py `ARMS`:
  - vp-noshare = (noshare, tape, `--value-profile 1 --splice 1`);
  - vp-rwlock = (rwlock, tape, `--value-profile 1 --splice 1 --pool-cap 32768`);
  - random-capture unchanged.
  - The V4 run set is the `v3` experiment in tools/run.py (V3_PROBLEMS, V3_ARMS, seeds 6000 + r, 120 s).
- Guard-only build for pre-V4 guided runs: `-DCF_NO_PERTURB` (fast_bug_deep_noperturb, `--fast bug_deep_noperturb`)
  keeps the three guard comparisons, instrumented; the innermost body writes a volatile sink, the output is never
  changed, nothing is counted or logged. Test: on each trigger input its output is byte-identical to sol.cpp's.
- Tests:
  - selftest;
  - replay of admitted entries, splice children included (tape_replay_check);
  - one smoke run per arm on each of the 3 deep problems with `--fast bug_deep_noperturb` (no bug can fire),
    reporting tests/s, arena peak, foreign-parent share vs 7/8 and the splice applied fraction.

OUTPUT: diff summary, smoke table, commit hash. Committing V3 freezes the design below.

## Step V4: The experiment (2 h, frozen design)
- Problems: the 3 deep problems from V1. Arms: vp-noshare, vp-rwlock, random-capture (reference).
- 8 workers, hunt mode, `--fast bug_deep`, time limit 120 s per run; a run without a bug is censored (+inf, as in
  tools/aggregate.py).
- n = 100 runs per arm per problem, seeds 6000–6099, randomised blocks (tools/run.py `--exp v3 --preset full`),
  one discarded warm-up (seed 999).
- Analysis, per problem:
  - one-sided Mann-Whitney U (vp-rwlock < vp-noshare), Holm-corrected over the 3 problems;
  - median ratio vp-rwlock / vp-noshare with 95% bootstrap CI (2,000 resamples);
  - H1 is supported if at least 1 problem is significant after Holm. All 3 are reported regardless.
  - Descriptive only: random-capture medians, foreign-parent share vs 7/8, censoring counts, wall time.
- ETA (recomputed from the V3 smoke tests/s, under the null that every arm needs the calibrated mean tests-to-bug,
  mean = median / ln 2 = 72,300 / 39,000 / 86,300 tests): per block 19.4 + 11.6 + 27.7 s of fuzzing + 9 × 0.3 s
  start-up ≈ 61 s, so 100 blocks ≈ 1.7 h. If the vp arms need twice as many tests, ≈ 2.6 h. If the ETA during the
  run exceeds 3 h, STOP and ask; no silent cuts.
- Run exactly this, nothing else.

OUTPUT: results table, statistics, H1 verdict, commit hash.

## Step V5: Report (1 h)
- Append the V4 results to docs/v3_results.md.
- Update README "Key results" and the summary paragraph, including the caveat above, whatever the outcome.

## Time budget

| Part | Hours |
|---|---|
| V1 (code 1 h, calibration ≤ 6 candidates × 2 rounds × ~5 min) | 2.5 |
| V2 | 2 |
| V3 | 2 |
| V4 (runs ≈ 1.7 h) | 2 |
| V5 | 1 |
| Total | ≈ 9.5 |

## Seeds (disjoint from all earlier ranges)
- Constant sampling: 8000.
- Calibration: 7000–7009.
- Experiment: 6000–6099.
- Smoke runs: 1000.

## Changes before the design freeze (2026-10-31, user-approved)
Decided from V2 cost data only, before any guided run on a deep bug, and applied in the V3 commit:
1. V2 deviation recorded: only fast_bug_deep carries trace-cmp; fast_sol and fast_bug are unchanged.
2. V4 sample size n = 100 per arm per problem (seeds 6000–6099) instead of 60, because V2 measured a vp overhead of
   ~0.92× instead of the assumed 2×, so n = 100 fits the original 2 h slot. Power and null-result wording updated.
3. Smoke runs use the guard-only CF_NO_PERTURB build instead of `--fast sol` (which has no trace-cmp, so a vp arm
   on it would have no value signal).
4. The deep_bug.hpp capture/rewrite helpers are excluded from coverage (no_sanitize_coverage), see V2 "Leftover check".
