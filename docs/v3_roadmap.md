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
| V1 | Deep bugs on 3 problems | 2.5 h | done | |
| V2 | trace-cmp value profile | 2 h | | |
| V3 | Cross-worker splice, origin, equal pool capacity, arms | 2 h | | |
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
- Power: with n = 60 per arm, the existing Mann-Whitney simulation gives a minimum detectable median ratio between
  2.5× (n = 30) and 1.6× (n = 100), so roughly 2×. A null result is reported as "no effect of 2× or more
  detected", not as "no effect".

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

OUTPUT: diff summary, overhead table, commit hash.

## Step V3: Cross-worker splice, origin, equal pool capacity, arms (2 h)
Scope: core/mutate.hpp, core/arena.hpp, core/pool.hpp, core/fuzzer.cpp, tools/run.py.

- Splice (`--splice 1`):
  - child = parent A's tape up to A's draw k, then donor B's tape from B's draw k;
  - k is uniform on [1, min(draws) − 1]; if min(draws) < 2, it falls back to a value op;
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
  - vp-rwlock = (rwlock, tape, `--value-profile 1 --splice 1`);
  - random-capture unchanged.
- Tests:
  - selftest;
  - replay of 50 admitted entries, splice children included (tape_replay_check);
  - one smoke run per arm on one deep problem with `--fast sol` (no bug can fire), reporting tests/s, arena peak and
    foreign-parent share.

OUTPUT: diff summary, smoke table, commit hash. Committing V3 freezes the design below.

## Step V4: The experiment (2 h, frozen design)
- Problems: the 3 deep problems from V1. Arms: vp-noshare, vp-rwlock, random-capture (reference).
- 8 workers, hunt mode, `--fast bug_deep`, time limit 120 s per run; a run without a bug is censored (+inf, as in
  tools/aggregate.py).
- n = 60 runs per arm per problem, seeds 6000–6059, randomised blocks (tools/run.py), one discarded warm-up.
- Analysis, per problem:
  - one-sided Mann-Whitney U (vp-rwlock < vp-noshare), Holm-corrected over the 3 problems;
  - median ratio vp-rwlock / vp-noshare with 95% bootstrap CI (2,000 resamples);
  - H1 is supported if at least 1 problem is significant after Holm. All 3 are reported regardless.
  - Descriptive only: random-capture medians, foreign-parent share vs 7/8, censoring counts, wall time.
- ETA: about 3 × 60 × (≈ 7 s + 2 × ≈ 15 s) ≈ 1.9 h, with vp runs assumed about 2× slower per test. Recomputed from
  V3's smoke tests/s before starting. If the ETA is over 3 h, STOP and ask; no silent cuts.
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
| V4 (runs ≈ 1.9 h) | 2 |
| V5 | 1 |
| Total | ≈ 9.5 |

## Seeds (disjoint from all earlier ranges)
- Constant sampling: 8000.
- Calibration: 7000–7009.
- Experiment: 6000–6059.
- Smoke runs: 1000.
