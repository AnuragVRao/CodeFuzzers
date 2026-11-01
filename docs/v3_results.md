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


## Post-hoc: paired sensitivity analysis and run census (2026-11-01)

POST-HOC, added after an external review of the report; the pre-registered analyses above (and in docs/v2_results.md
and tools/aggregate.py) remain the primary results and are unchanged. Command: `python3 tools/paired_check.py`
(read-only over results/raw/; `--selftest` in tools/selftest.sh).

Why: every arm of block r runs with the same `--seed base + r` (tools/run.py), so runs of one block are paired, which
Mann-Whitney ignores. Method: Wilcoxon signed-rank on ln(tests_b / tests_a) per block, zero_method "wilcox" (zero
differences dropped, counted below), same sidedness as the original test, Holm within the original family. The
estimand is the median over blocks of the paired ratio tests_b / tests_a (not the ratio of medians above), with a 95%
block-bootstrap CI (2,000 resamples, seed 20261101 + comparison index).

### Census and seed check

Censored = no bug and wall_s >= config.time_limit; infra = no bug and wall_s < time_limit; counted from each run JSON.

```
## hunt: 2970 runs, expected 99 cells x 30 = 2970; found 2970, censored 0, infra 0; cells with n != 30: 0
   seed check (seed == 1000 + repeat, block_seed where present): OK
## hunt-focus: 900 runs, expected 9 cells x 100 = 900; found 900, censored 0, infra 0; cells with n != 100: 0
   seed check (seed == 1000 + repeat, block_seed where present): OK
## pilot: 1800 runs, expected 9 cells x 200 = 1800; found 1800, censored 0, infra 0; cells with n != 200: 0
   seed check (seed == 5000 + repeat, block_seed where present): OK
## v3: 900 runs, expected 9 cells x 100 = 900; found 900, censored 0, infra 0; cells with n != 100: 0
   seed check (seed == 6000 + repeat, block_seed where present): OK
```

All cells have exactly the expected repeats; 0 censored and 0 infra runs in every cell of every experiment.
hunt: 11 hard-tier problems x 3 arms x workers {1, 8, 20} x 30 repeats = 2,970.

### Results

Exploratory hunt (66 comparisons): 0 of 66 significant after Holm (full table: run the script). At 1 worker rwlock and
noshare are the same computation (same seed, one pool): 30 of 30 zero differences, rho = 1, in all 11 problems.

### confirmatory (6 comparisons, Holm over 6)

| problem | W | b / a | alt | n | zeros | rho | median paired ratio [95% CI] | p (Wilcoxon) | p_Holm |
|---|---:|---|---|---:|---:|---:|---|---:|---:|
| longest_common_substring | 8 | noshare / random | two-sided | 100 | 0 | 0.01 | 0.65 [0.55, 1.20] | 0.132 | 0.658 |
| longest_common_substring | 8 | rwlock / noshare | two-sided | 100 | 0 | 0.46 | 0.77 [0.56, 1.06] | 0.153 | 0.658 |
| majority_voting | 8 | noshare / random | two-sided | 100 | 0 | 0.05 | 0.94 [0.56, 1.69] | 0.797 | 1 |
| majority_voting | 8 | rwlock / noshare | two-sided | 100 | 1 | 0.45 | 1.04 [0.97, 1.12] | 0.348 | 1 |
| range_linear_add_range_min | 8 | noshare / random | two-sided | 100 | 0 | 0.10 | 0.86 [0.76, 1.21] | 0.926 | 1 |
| range_linear_add_range_min | 8 | rwlock / noshare | two-sided | 100 | 2 | 0.42 | 1.08 [1.00, 1.47] | 0.092 | 0.552 |

0 of 6 significant after Holm (p_Holm < 0.05)

### pilot (descriptive) (6 comparisons, Holm over 6)

| problem | W | b / a | alt | n | zeros | rho | median paired ratio [95% CI] | p (Wilcoxon) | p_Holm |
|---|---:|---|---|---:|---:|---:|---|---:|---:|
| longest_common_substring | 8 | tape-noshare / random-capture | two-sided | 200 | 0 | -0.05 | 1.05 [0.68, 1.43] | 0.857 | 0.857 |
| longest_common_substring | 8 | tape-rwlock / random-capture | two-sided | 200 | 1 | 0.16 | 0.60 [0.50, 0.84] | 0.000598 | 0.0012 |
| majority_voting | 8 | tape-noshare / random-capture | two-sided | 200 | 0 | 0.01 | 3.54 [2.34, 5.19] | 4.06e-14 | 1.22e-13 |
| majority_voting | 8 | tape-rwlock / random-capture | two-sided | 200 | 0 | 0.01 | 4.03 [2.99, 5.80] | 3.28e-15 | 1.31e-14 |
| range_linear_add_range_min | 8 | tape-noshare / random-capture | two-sided | 200 | 0 | 0.08 | 4.82 [4.00, 5.79] | 1.29e-23 | 7.75e-23 |
| range_linear_add_range_min | 8 | tape-rwlock / random-capture | two-sided | 200 | 0 | 0.06 | 6.49 [5.31, 8.80] | 2.02e-22 | 1.01e-21 |

5 of 6 significant after Holm (p_Holm < 0.05)

The pilot pre-registered a median-ratio criterion, not a test; these p values are descriptive. tape-rwlock on
longest_common_substring has a median paired ratio of 0.60 [0.50, 0.84], a different estimand from the pre-registered
ratio of medians (0.793); the criterion and the STOP verdict are unchanged.

### v3 H1 (3 comparisons, Holm over 3)

| problem | W | b / a | alt | n | zeros | rho | median paired ratio [95% CI] | p (Wilcoxon) | p_Holm |
|---|---:|---|---|---:|---:|---:|---|---:|---:|
| range_add_range_min | 8 | vp-rwlock / vp-noshare | less | 100 | 0 | 0.40 | 0.47 [0.39, 0.57] | 1.98e-12 | 5.94e-12 |
| range_affine_range_sum | 8 | vp-rwlock / vp-noshare | less | 100 | 0 | 0.33 | 0.63 [0.52, 0.81] | 7.73e-06 | 8.9e-06 |
| range_set_range_composite | 8 | vp-rwlock / vp-noshare | less | 100 | 0 | 0.14 | 0.71 [0.41, 0.85] | 4.45e-06 | 8.9e-06 |

3 of 3 significant after Holm (p_Holm < 0.05)

Same conclusion as the frozen analysis: H1 supported on all three problems.

### Pre-registration timing (git commit times vs earliest run-file mtime, UTC)

| result | plan / freeze commit | data | pre-registered? |
|---|---|---|---|
| hunt-focus | rule f2392e3 2026-10-21 18:44, problems 078b143 18:53 | 2026-10-22 05:09–05:11 (stamped 078b143) | yes |
| pilot | plan 90cc267 2026-10-30 19:39:51 (Amendment 1 b94f7ce 19:47:39) | 19:47:52–19:54:18 (stamped b94f7ce) | yes |
| v3 H1 | long plan 3ff4493 12:57 replaced by short plan 3ecab06 13:06; design + test + n = 100 frozen b518f21 13:40; analysis 022da45 13:44 | counted 13:45–14:36 (stamped 022da45) | yes; 21 aborted runs (13:41–13:42, results/raw/v3_aborted/) printed tests-to-bug in run.py progress lines before 022da45, unused |
| shrink S1 | a4a6aa4 2026-10-31 05:24:42 | EVAL from 05:25:04 | yes |
| shrink S2 | 618f6fc 08:37:45 | EVAL_S2 ~08:38–10:21 | evaluation yes; design post-hoc (after S1 EVAL) |

### Coverage-map collisions (descriptive)

The largest cov_features of any run is 3,931 (hunt, frequency_table_of_tree_distance); features >= occupied edge
slots, so with uniform hashing into 65,536 slots at most 1 - (1 - 1/65536)^3930 ≈ 5.8% of edges share a slot (v3:
max 979 features, ≤ 1.5%; value-profile map max 486, ≤ 0.7%). All arms use the same binaries and map.
