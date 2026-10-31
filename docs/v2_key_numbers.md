# v2 key numbers: traceability

One row per headline number the report quotes. "Script" is the committed script that produces the number, at the
commit that last changed it; "Reproduced" records re-running that script on 2026-10-31 (commit 325122f) and comparing
with the source. Scripts read saved outputs only (results/ is gitignored and identified by the manifests). Builds are
never mixed: v1 numbers come from v1-build runs, v2 numbers from v2-build runs.

## v1 (v1 build; runs at commits 078b143 / 672be82; aggregated 2026-10-22)

| Number | Meaning | Source | Script (commit) | Raw data | Reproduced |
|---|---|---|---|---|---|
| p_Holm >= 0.47 for all 6 confirmatory comparisons (LCS noshare/random 0.47; the other five 1.00) | v1 confirmatory hunt (hunt-focus, n = 100, 8 workers), Mann-Whitney U, Holm within the confirmatory family | README key-results table; results/summary.json hunt_tests | tools/aggregate.py (0dbb9f8) | results/raw/hunt-focus/ in the v1 archive (docs/v1_archive.sha256) | yes: summary.json identical except generated_at |
| 0.61 [0.41, 1.01] | longest_common_substring, median tests-to-bug noshare / random (8 workers, n = 100), 95% bootstrap CI | README; summary.json (ratio 0.612392) | tools/aggregate.py (0dbb9f8) | as above | yes |
| 8.86x / 8.72x | v1 scale: speed-up at 20 workers vs noshare at 1 worker, rwlock / noshare, K = 0 (weak scaling, range_add_range_min, zalgorithm, vertex_add_path_sum) | summary.json meta.headline (speedup_20_rwlock_k0, speedup_20_noshare_k0); README | tools/aggregate.py (0dbb9f8) | results/raw/scale/ in the v1 archive | yes |

## v2 Step 2e (v2 build 99e05aa; plan docs/v2_pilot_plan.md at 90cc267)

| Number | Meaning | Source | Script (commit) | Raw data | Reproduced |
|---|---|---|---|---|---|
| MV 0.8825 / 0.9669 [0.8377, 0.9918]; RLARM 0.9165 / 0.9583 [0.8214, 0.9849]; LCS 0.8395 / 0.9773 [0.8667, 0.9894] | Part 2 criterion (a), draw-level: mut_changed_input / median mut_similarity over changed children [IQR]; (a) PASS | docs/v2_results.md "Step 2e Part 2" | tools/part2.py measure() (99e05aa) | results/part2/, 61 file hashes in that section | yes (recomputed from the saved outputs) |
| random-capture 319.5 / 196.0 / 289.5; tape-noshare 1,238.5 / 1,041.5 / 357.5; tape-rwlock 1,135.5 / 1,206.5 / 229.5 | Pilot median generated tests-to-bug (MV / RLARM / LCS), n = 200 per arm, 0 censored | docs/v2_results.md "Step 2e Part 3" | tools/pilot_report.py (964a920) | results/raw/pilot/, docs/v2_pilot_raw.sha256 (6,600 files) | yes: output byte-identical to the reviewed report |
| 3.876, 3.554, 5.314, 6.156, 1.235, 0.793 | Tape / random-capture median ratios (MV noshare, MV rwlock, RLARM noshare, RLARM rwlock, LCS noshare, LCS rwlock); (b) FAIL, verdict STOP | as above | tools/pilot_report.py (964a920) | as above | yes |
| [2.974, 5.044], [2.518, 5.079], [4.064, 6.786], [4.730, 7.893], [0.934, 1.624], [0.615, 0.981] | Post-hoc 95% bootstrap CIs of the six ratios (same order; 2,000 resamples, seed 20261030) | docs/v2_results.md "Exploratory (post-hoc) analysis" (c) | tools/pilot_posthoc.py (964a920) | as above | yes |
| root-found 58/86/108/129/25/13 of 200; root fraction 0.106-0.130 | Post-hoc: bugs found by roots, per tape arm (same order), and median whole-run root fraction | same section (a), (b) | tools/pilot_posthoc.py (964a920) | as above | yes |
| child productivity 0.170, 0.196, 0.089, 0.061, 0.783, 1.301 | Post-hoc, model-based relative child productivity (same order) | same section (d) | tools/pilot_posthoc.py (964a920) | as above | yes |
| 3.8 SE; 0.205 | Post-hoc note on (d): MV tape-noshare observed vs predicted root share; productivity from the observed share | same section, note of 2026-10-30 | none (inline computation, see below) | as above | not by a committed script |
| 0.447 / 0.446 (n = 50); 0.0378 / 0.0372 (n = 200) | False-PROCEED rate of criterion (b) under a no-effect null, exponential / geometric, 200,000 replicates | docs/v2_pilot_plan.md (Disclosures); docs/v2_roadmap.md Step 2e | tools/fp_sim.py (5831353) | none (simulation, seed 20261030) | yes: 0.4467 / 0.4457 / 0.0378 / 0.0372 |

## v2 Step S (plans docs/shrink_plan.md at a4a6aa4, docs/shrink_plan_s2.md at 618f6fc)

| Number | Meaning | Source | Script (commit) | Raw data | Reproduced |
|---|---|---|---|---|---|
| 69 / 140, 11 / 30, 3 / 5 | Floors (tokens / bytes) for MV / RLARM / LCS, verified on hand-built inputs | docs/shrink_plan.md Yardstick | none (inline predicate runs, see below) | none | not by a committed script |
| old 378 / 187 / 3; S1 113 / 174 / 3; S2 112 / 30 / 3 | Median after-tokens per distinct input, MV / RLARM / LCS | docs/v2_results.md "Step S: shrinker evaluation", "Step S2: shrinker evaluation" | tools/shrink_report.py (fda85cf), tools/shrink_report_s2.py (250845b) | results/shrink/eval*/summary.json (sha256 in those sections) | yes: every output line found verbatim |
| S1 after/floor 1.64 / 15.82 / 1.00; S2 1.62 / 2.73 / 1.00; at floor S2 0.1% / 5.5% / 100% | Gap to the floor and fraction at the floor | as above | as above | as above | yes |
| RLARM S2/S1 0.201 [0.130, 0.324], 922 smaller / 19 equal / 0 larger | Paired S2 vs S1 after-tokens on the same distinct inputs | "Step S2: shrinker evaluation" | tools/shrink_report_s2.py (250845b) | as above | yes |
| 1,973 / 1,973 | Cold-start replay of every final S1 and S2 input | both Step S sections | tools/shrink_run.py --replay | results/shrink/eval/, eval_s2/ | recorded from the run logs (not re-run: re-judging all inputs is a re-run of the replay) |

## Numbers without a committed producing script
Listed rather than fixed:
- 3.8 SE and 0.205 (post-hoc note on (d)): computed inline on 2026-10-30 from tools/pilot_posthoc.py's quantities.
- The floors and the majority_voting multiple-of-64 tests (63/64/65/127/128/129 copies; [0, 63) vs [1, 64)): inline
  runs of tools/shrink.py's Judge on hand-built inputs.
- Post-hoc diagnosis (S1): header-count table and the RLARM hand check (42 of 45 lines removable; 30 tokens / 231
  bytes): inline read-only scripts.
- Post-hoc majority_voting check (S2): right end = n in 965 of 967: inline read-only script.
- v2-build lock-strategy measurements (Step 2b T4, Step 2c T2, follow-up A 1-worker cells): regression gates comparing
  two builds, run with scratch scripts; they are not quoted as scaling results and must not be mixed with the v1
  scaling numbers above.
- S2 DEV comparison (7 smaller / 20 equal / 0 larger): computed inline from results/shrink/dev_s2 and
  dev_s1_cap10k.
