# v3 results (append-only)

Plan: docs/v3_roadmap.md (short v3 plan, design frozen at b518f21; analysis committed at 022da45 before the counted
runs). Machine: i7-13650HX laptop, WSL2, 8 workers pinned per tools/run.py `CPU_ORDER`.

Caveat (also in the README): deep bugs are synthetic, guarded by comparison chains that value profiling is designed to
exploit. A positive H1 shows that sharing helps on this bug class; it does not show that sharing helps on typical
competitive-programming bugs (off-by-one, overflow, missed edge cases).

## V1: deep bugs (2026-10-31, commit 39e9f40)

sol_bug_deep.cpp = sol.cpp + `if (n >= C1) { if (a[0] >= C2) { if (sum(a) mod M == C3) <first output integer + 1> } }`
(core/deep_bug.hpp). Constants from 2,000 sampled inputs (`random.Random(8000)`), target pass rate p = 0.026 per guard,
written by tools/deep_calib.py. Calibration: random-capture, 8 workers, 10 runs, seeds 7000–7009, 60 s limit, band
15,000–120,000 generated tests to bug. The first 3 candidates in manifest order all qualified in round 0 (no
adjustment); Dataset/bugs_deep.json has every number.

| problem | C1 | C2 | M | C3 | per-guard rates | trigger (verifier / sol / deep) | median [q1, q3] tests-to-bug | censored |
|---|---:|---:|---:|---:|---|---|---|---:|
| range_add_range_min | 158 | 929,744,142 | 38 | 33 | 0.026 / 0.026 / 0.026 | ok / ok / WA | 50,142 [23,139, 79,876] | 0 |
| range_affine_range_sum | 158 | 975,574,924 | 38 | 0 | 0.026 / 0.026 / 0.026 | ok / ok / WA | 27,042 [14,694, 58,820] | 0 |
| range_set_range_composite | 158 | 975,574,925 | 38 | 32 | 0.026 / 0.026 / 0.026 | ok / ok / WA | 59,818 [21,324, 126,648] | 0 |

All 30 calibration bug inputs pass all three guards (checked from the saved inputs).

## V2: trace-cmp value profile (2026-10-31, commit 59755dd)

Only fast_bug_deep carries `-fsanitize-coverage=trace-pc,trace-cmp`; fast_sol and fast_bug are unchanged. Feature =
hash(compare PC, floor(log2(|a − b| + 1))) in a second 64 KiB map; `--value-profile 1` admits on a new bit in either map.
On every trigger the three guard compares are visible with distances 1, 1, 0 (GCC compiles `g >= C` as `g > C − 1`).

| problem | tests/s, trace-pc only | trace-cmp, profile off | trace-cmp, `--value-profile 1` |
|---|---:|---:|---:|
| range_add_range_min | 10,148 | 0.98× | 0.92× |
| range_affine_range_sum | 9,093 | 0.98× | 0.93× |
| range_set_range_composite | 8,718 | 0.97× | 0.92× |

(8 workers, random strategy, 40,000 tests, median of 3.) Admission check on a scratch trace-cmp build of sol.cpp
(tape-rwlock, 20,000 tests): 80 entries without, 106 with the value profile, identical edge coverage.

## V3: splice, origin, equal capacity (2026-10-31, commit b518f21, design frozen)

Pre-freeze changes (user-approved, from V2 cost data only): n = 100 for V4; a guard-only CF_NO_PERTURB build for smoke
runs (output byte-identical to sol on every trigger); the deep_bug.hpp output helpers excluded from coverage (24 of
65 compare sites on a trigger came from them; afterwards 0; vp_features 519/256/453 → 486/226/400).
Replay: all 124 admitted entries of a vp-rwlock run (39 splice children) regenerate their stored input hash.

Smoke (60,000 tests, seed 1000, fast_bug_deep_noperturb, 8 workers):

| problem | arm | tests/s | arena peak | pool entries | foreign parent (all / admitted) | splice share of ops | splice fallback | dup rate |
|---|---|---:|---:|---:|---|---:|---:|---:|
| range_add_range_min | vp-noshare | 11,526 | 7.2 MB | 960 | 0 / 0 of 678 | 0.142 | 0.049 | 0.082 |
| range_add_range_min | vp-rwlock | 11,284 | 1.1 MB | 119 | 0.874 / 71 of 88 | 0.139 | 0.061 | 0.080 |
| range_add_range_min | random-capture | 10,735 | 0 | – | – | – | – | 0 |
| range_affine_range_sum | vp-noshare | 10,742 | 2.7 MB | 516 | 0 / 0 of 340 | 0.140 | 0.046 | 0.094 |
| range_affine_range_sum | vp-rwlock | 10,432 | 0.3 MB | 67 | 0.877 / 38 of 44 | 0.143 | 0.033 | 0.085 |
| range_affine_range_sum | random-capture | 9,255 | 0 | – | – | – | – | 0 |
| range_set_range_composite | vp-noshare | 9,869 | 5.3 MB | 762 | 0 / 0 of 516 | 0.144 | 0.046 | 0.072 |
| range_set_range_composite | vp-rwlock | 9,520 | 0.9 MB | 108 | 0.874 / 62 of 73 | 0.141 | 0.043 | 0.070 |
| range_set_range_composite | random-capture | 8,729 | 0 | – | – | – | – | 0 |

Skipped duplicates count as generated tests (tests_before = `completed`, incremented for every test); the duplicate
set is per worker in both vp arms; random-capture skips no duplicates.

## V4: the pre-registered experiment (2026-10-31, runs from commit 022da45)

3 deep problems × 3 arms × n = 100, seeds 6000–6099, 8 workers, hunt, 120 s limit, randomised blocks; 900 runs, none
failed, none censored, all stamped 022da45 with a clean tree. Analysis: `python3 tools/v3_report.py`, unchanged.
An earlier start (21 finished runs + 1 partial, before the analysis existed) was set aside unused in
results/raw/v3_aborted/ (roadmap, "V4 execution note").

| problem | arm | median tests-to-bug | q1 | q3 | median wall s | tests/s | foreign parent (all / admitted) | foreign donor (admitted splices) |
|---|---|---:|---:|---:|---:|---:|---|---:|
| range_add_range_min | vp-noshare | 15,778 | 10,939 | 25,797 | 1.4 | 11,146 | 0.000 / 0.000 | 0.000 |
| range_add_range_min | vp-rwlock | 7,774 | 3,359 | 12,208 | 0.7 | 10,818 | 0.874 / 0.856 | 0.855 |
| range_add_range_min | random-capture | 36,546 | 14,944 | 71,078 | 3.6 | 10,222 | – | – |
| range_affine_range_sum | vp-noshare | 15,002 | 9,007 | 24,540 | 1.4 | 10,366 | 0.000 / 0.000 | 0.000 |
| range_affine_range_sum | vp-rwlock | 9,452 | 4,037 | 17,203 | 0.9 | 10,150 | 0.875 / 0.850 | 0.868 |
| range_affine_range_sum | random-capture | 43,590 | 23,072 | 83,625 | 4.7 | 9,262 | – | – |
| range_set_range_composite | vp-noshare | 19,941 | 11,873 | 30,784 | 2.0 | 9,706 | 0.000 / 0.000 | 0.000 |
| range_set_range_composite | vp-rwlock | 12,016 | 6,343 | 18,222 | 1.3 | 9,569 | 0.875 / 0.866 | 0.870 |
| range_set_range_composite | random-capture | 42,995 | 18,910 | 75,756 | 4.9 | 8,766 | – | – |

H1: one-sided Mann-Whitney U (vp-rwlock < vp-noshare), Holm over the 3 problems; censored = +inf.

| problem | ratio vp-rwlock / vp-noshare [95% CI] | p (one-sided) | p_Holm |
|---|---|---:|---:|
| range_add_range_min | 0.49 [0.37, 0.63] | 5.27e-11 | 1.58e-10 |
| range_affine_range_sum | 0.63 [0.48, 0.87] | 4.71e-4 | 4.71e-4 |
| range_set_range_composite | 0.60 [0.45, 0.83] | 4.33e-6 | 8.66e-6 |

**Verdict: H1 is supported** (supported if at least 1 problem is significant after Holm; all 3 are, and all 3 are
reported).

Descriptive (not tested): bug-finding tests that were children of a pool entry / with a foreign parent / from a splice
/ with a foreign donor, out of 100 bugs each:

| problem | vp-noshare | vp-rwlock |
|---|---|---|
| range_add_range_min | 95 / 0 / 27 / 0 | 98 / 85 / 29 / 23 |
| range_affine_range_sum | 95 / 0 / 29 / 0 | 100 / 90 / 32 / 29 |
| range_set_range_composite | 95 / 0 / 45 / 0 | 96 / 86 / 49 / 44 |

Both vp arms also needed fewer tests than random-capture (medians 36,546–43,590); that comparison was descriptive only.
Note that the guided arms' medians (7,774–19,941) are below the calibration band (15,000–120,000), which was set for
random-capture only.
