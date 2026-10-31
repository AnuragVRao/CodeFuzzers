# CodeFuzzers
Parallel differential fuzzer for competitive-programming solutions. Course project:
code must be small, readable, and to the point. Prefer fewer files. No frameworks
beyond those listed here.

v2 work follows docs/v2_roadmap.md. Read it before any v2 task.
v3 work follows docs/v3_roadmap.md. Read it before any v3 task.

## Layout
- Dataset/problems/<group>/<name>/  dataset; groups: arrays, graphs, strings.
  Shared headers in Dataset/common/. Problem list comes from Dataset/manifest.json.
  (never modify unless explicitly asked; generators got a size knob, sol_bug.cpp was added)
  Exception (team-approved): Dataset/common/random.h may be modified for random-tape support,
  provided tools/golden_gen.py --check passes when no tape is supplied.
  Exception (user-approved 2026-10-31, v3): sol_bug_deep.cpp (sol.cpp + one guarded perturbation from
  core/deep_bug.hpp, constants written only by tools/deep_calib.py) and Dataset/bugs_deep.json may be added.
- fuzz_config.json  per-problem settings: {"<problem>": {"max_size": N}}
- requirements.txt  numpy, scipy, matplotlib (pinned); nothing else for Python
- core/             C++17, header-light:
    fs_runtime.cpp  fork-server + trace-pc coverage runtime linked into every binary
    server.hpp      client side (posix_spawn, pipes, memfd coverage map)
    pool.hpp        Pool interface + 5 strategies (global, sharded, rwlock, snapshot, noshare)
    fuzzer.cpp      the multi-threaded fuzzer (scale / hunt; v2 --recipes tape, --tape-capture, --op-log), JSON summary
    pool_bench.cpp  pool-only micro-benchmark and --check; smoke.cpp single-threaded e2e test
    compare.hpp     token comparison, checker_outcome(), hash_bytes()
    deep_bug.hpp    v3 deep-bug guard + output perturbation, included by sol_bug_deep.cpp (built as fast_bug_deep)
    arena.hpp       v2 tape arena + TapeHandle/TapeEntry; mutate.hpp  v2 tape mutation operators
    part2.cpp       v2 Step 2e Part 2 children generator (run by tools/part2.py)
    tape_file_runtime.cpp  file-based tape sessions (CF_TAPE_* env vars) for the build/tape/ generators (Step S)
    tests/          fork-server edge cases (server_test + crash/hang/exit3/exit_code/gen_named/gen_seedonly),
                    checker_test, tape_test (random.h sessions), tape_server_test + gen_tape_toy (tape memfd),
                    tape_replay_check (admitted entries replay), arena_test (arena stress, plain + TSan),
                    golden_gen.json (golden generator hashes)
- tools/            Python 3.12 (stdlib + requirements.txt):
    build.py        builds everything into build/ (--force rebuilds all)
    run.py          experiment orchestrator (randomised blocks, resumable, git-stamped)
    flatten.py -> aggregate.py -> plots.py   raw JSON -> runs.csv -> summary.json -> charts
    results_table.py  README key-results table from summary.json
    sanity.py       plain gen/brute/fast check; tier_bugs.py measures planted-bug rates
    shrink.py, shrink_scaling.py, bug_gallery.py, repro.py   shrinking and bug gallery (shrink.py: v2 tape +
                    ddmin shrinker by default, the v1 generator-space shrinker behind --old)
    shrink_run.py   Step S driver over the DEV / EVAL bug sets (capture check, new/old shrinker, cold replay);
                    shrink_test.py  shrinker negative controls and determinism
    llm.py          Ollama explain/gen (random_api.txt is part of the gen prompt)
    problems.py     shared helpers (manifest, compile, run_test, run_checker); style.py strategy colours
    selftest.sh     build + all self-tests, PASS/FAIL per item
    golden_gen.py   golden generator hashes (--check: runtime-linked and build/plain/ generators)
    checker_agree_test.py  C++ vs Python checker-outcome mapping
    deep_calib.py   v3 Step V1: deep-bug constants (sampling), trigger check, random-capture calibration
    replay_first_bugs.py   replays v1 first bugs (Step 0.2 evidence -> results/derived/)
    analyze.py, server.py, e2e_test.sh   analysis server (upload, queue, SSE) and its end-to-end test
    part2.py        v2 Part 2 pipeline + mut_similarity; fp_sim.py  pilot false-PROCEED simulation
    part2_oplog.py  Part 2 op-log analysis; pilot_report.py  pilot criterion (b) report;
                    pilot_posthoc.py  post-hoc pilot analysis (root/child, bootstrap CIs, rate decomposition)
    shrink_report.py, shrink_report_s2.py   Step S / S2 EVAL reports (old, S1, S2 shrinkers)
- docs/             v2_roadmap.md (v2 plan + status), v3_roadmap.md (v3 plan + status), tape_design.md (v2 spec as built), v2_pilot_plan.md
                    (pre-registration), v2_results.md (append-only results) + v2_pilot_raw.sha256 (pilot raw-output
                    manifest), shrink_plan.md / shrink_plan_s2.md (frozen Step S / S2 plans), known_issues.md,
                    v1_data_archive.md + v1_archive.sha256, DEMO.md
- examples/         sample uploads for the analysis server (incl. _guardrails/)
- .gitattributes    *.md text eol=lf
- build/            compiled binaries (gitignored); build/plain/ = plain binaries for Python tools;
                    build/tape/ = generators with tape_file_runtime.o (Step S shrinker)
- results/          run outputs (gitignored): raw/<experiment>/ (v2: raw/pilot/), runs.csv, summary.json,
                    charts/, bugs/ (gallery), llm/ (answers + prompts), derived/ (Step 0.2 replay), part2/,
                    shrink/<set>[_old]/ (Step S), deep_calib/<problem>/ (v3 V1)
- dashboard/        Vite + React + Recharts, reads results/summary.json, no backend;
                    Node 22 (.nvmrc) via nvm: `source ~/.nvm/nvm.sh` before npm

## Dataset conventions
- reference = brute.cpp, fast = sol.cpp (later: sol_bug.cpp with a planted bug)
- generator: ./generator <seed> [size]; prints test to stdout. Some problems also have
  gen/generator_alt_1.cpp (a second "variant").
- compile flags: g++ -O2 -std=c++17 -I Dataset/common -I <problem> -I <problem>/gen
- a generator exiting non-zero means "skip this seed", not a bug
- comparison: problems with checker_kind "exact-match" use token-wise comparison;
  the 5 "custom" ones run checker.cpp as: checker <input> <output> <answer>
- Outcome of one test:
  * generator exits non-zero          → "gen_skip" (not counted)
  * reference crashes or times out    → "invalid" (not a bug; counted separately)
  * fast crashes                      → bug, kind "RE"
  * fast times out                    → bug, kind "TLE"
  * both exit 0, outputs disagree     → bug, kind "WA"
  * custom checker (testlib exit code; checker_outcome() in core/compare.hpp, same mapping in
    tools/problems.py): 0 → "ok"; 1 _wa, 2 _pe, 4 _dirt, 8 _unexpected_eof → bug, kind "WA";
    3 _fail → "ref_fail" (reference judged wrong; not a bug, counted separately);
    killed by a signal, timed out, or any other exit code → "checker_error" (not a bug, counted
    separately). The first ref_fail / checker_error recipe is stored in the run JSON.
- Sizes are always clamped to max_size from fuzz_config.json.
- tests_to_bug = number of tests up to and including the first failing one (always >= 1).
- Dataset/bugs.json: one planted bug per problem with measured "rate" (% at sizes 5/20/max),
  "tier" (hard = all rates <= 15 %) and "kind"; regenerate with tools/tier_bugs.py.
  Note: suffixarray and number_of_substrings carry the same bug (shared SA-IS code).

## Design rules (do not change without being asked)
- A pool entry is a recipe (variant, size, seed) that reached new coverage, never raw
  input text. Mutation keeps the variant, perturbs size (clamped), draws a fresh seed.
  v2 (tape) recipes follow docs/tape_design.md. The v1 rule stays in force for all v1
  experiments and all scale experiments.
- v2 tape arena (core/arena.hpp): tape words + draw logs of admitted v2 entries live in one
  process-wide, append-only arena; a v2 pool entry (TapeEntry) holds only a handle into it.
  The pool is a template on its entry type; v1 and scale runs use Entry and never touch the arena.
- The shared pool lives only in C++. Python never touches it during a timed run.
- Pool strategies: global mutex, sharded mutexes, shared_mutex (readers-writers),
  RCU-style snapshot (atomic shared_ptr swap), and no-sharing baseline.
- Solutions run through a fork-server: each binary is linked with a runtime that
  forks before main() on request. Each worker thread owns its OWN server processes
  and talks to them via pipes. Worker threads themselves NEVER call fork().
- Coverage binaries are built with -no-pie so coverage IDs (hashed PCs) are stable across runs.
- Coverage: g++ -fsanitize-coverage=trace-pc; runtime hashes (prev_pc, pc) into a
  64 KiB map of saturating edge hit counts in shared memory. Coverage = edge hit-count
  buckets (AFL-style {1},{2},{3},{4-7},{8-15},{16-31},{32-127},{128+}); the pool bitmap
  stores one bit per (edge, bucket). "cov_features" = popcount of that bitmap.
  v3 value profile (docs/v3_roadmap.md V2): only fast_bug_deep is built with trace-pc,trace-cmp; with
  --value-profile 1 the coverage memfd is 2 x 64 KiB (edge map, then a value-profile map of (compare PC,
  floor(log2(|a-b|+1))) features) and admission is on a new bit in either half; "vp_features" = popcount of
  the second half. Without the flag everything above is unchanged.
- Timed region = worker loop only. Build, shrink, aggregation, and LLM calls are outside it.
- Two modes: "scale" (fixed test count, never stops early) and "hunt" (all workers
  stop on the first mismatch).
- Optional knob: extra pool reads/writes per test, to make lock contention measurable.
- Workloads: "scale" uses sol.cpp (correct; never stops early). "hunt" uses
  sol_bug.cpp; time-to-bug comparisons use only tier "hard" problems.
- No-sharing baseline = each worker keeps its OWN private pool and coverage map.
  Sharing methods share one pool and one global coverage map.
- Three-way comparison: "random" (no pool, no guidance: every recipe random) vs
  "noshare" (private guidance per worker) vs a sharing strategy (shared guidance).
- Scale experiments use --recipes random so every strategy does identical work per test;
  only synchronisation differs. Hunt experiments use guided recipes.
- Randomised block design (tools/run.py): repeat r is one block containing every configuration of
  the experiment, shuffled with random.Random(1000 + r); a discarded warm-up run starts each session.
  Machine drift therefore cannot line up with one strategy.
- Scale = weak scaling: tests = 2500 x workers; speed-up = throughput ratio (tests/s vs noshare @ 1).
- Scale results are only compared within one build (commit). Never mix v1-build and v2-build scale
  numbers in one comparison.
- "hunt" is exploratory (30 repeats, all hard-tier problems); "hunt-focus" (100 repeats, 8 workers,
  the 3 hard-tier problems with the most tests-to-bug; constant FOCUS_PROBLEMS in tools/run.py,
  recorded in results/raw/hunt-focus/focus.json) is the confirmatory test with its own Holm family.
  Confirmatory problems: chosen by a difficulty rule (largest median tests-to-bug over all
  three strategies) AFTER the exploratory hunt finished (hunt_full.log 2026-10-21 18:22 UTC;
  rule committed f2392e3 18:44 UTC), and BEFORE confirmatory (hunt-focus) data collection:
  majority_voting, range_linear_add_range_min, longest_common_substring.
- Statistics (tools/aggregate.py docstring has every formula): medians + IQR; censored hunts
  count as +inf; Mann-Whitney U with Holm correction per family; bootstrap CI of median ratios;
  simulated minimum detectable effect; LLM hits vs exact Poisson-binomial / binomial baselines.
- Workers are pinned to CPUs in the order 0,2,4,...,18,1,3,...,19 (one hyper-thread per core first).
- LLM layer (tools/llm.py): local Ollama at $OLLAMA_URL (default http://localhost:11434),
  outside the timed region. Prompts must never contain Dataset/bugs.json, sol.cpp or the
  gallery's description/trigger/category; changed comments in sol_bug.cpp are blanked.

## Environment
WSL2 Ubuntu 24.04 (mirrored networking for Ollama on Windows), i7-13650HX (6P+8E cores,
20 logical CPUs), g++ 13.3, Python 3.12, Node 22.

## Working style
- Small steps. Do only what the current prompt asks; do not start the next step.
- End every step by running the test command given and showing its real output.
- tools/selftest.sh must pass before committing.
- Header changes trigger rebuilds: problem binaries (tools/build.py and build/plain/ via
  problems.compile) depend on every .h/.hpp in their source dir and -I dirs (problems.header_deps);
  tools depend on fs_runtime.o and the core headers they list.
- Do not add dependencies without asking (Python: requirements.txt; JS: dashboard/package.json).
- The repo path contains a space. Always call subprocess with argument lists, never
  shell strings; quote paths in any shell command.
