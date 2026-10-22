# CodeFuzzers
Parallel differential fuzzer for competitive-programming solutions. Course project:
code must be small, readable, and to the point. Prefer fewer files. No frameworks
beyond those listed here.

## Layout
- Dataset/problems/<group>/<name>/  dataset; groups: arrays, graphs, strings.
  Shared headers in Dataset/common/. Problem list comes from Dataset/manifest.json.
  (never modify unless explicitly asked; generators got a size knob, sol_bug.cpp was added)
- fuzz_config.json  per-problem settings: {"<problem>": {"max_size": N}}
- requirements.txt  numpy, scipy, matplotlib (pinned); nothing else for Python
- core/             C++17, header-light:
    fs_runtime.cpp  fork-server + trace-pc coverage runtime linked into every binary
    server.hpp      client side (posix_spawn, pipes, memfd coverage map)
    pool.hpp        Pool interface + 5 strategies (global, sharded, rwlock, snapshot, noshare)
    fuzzer.cpp      the multi-threaded fuzzer (scale / hunt), JSON summary
    pool_bench.cpp  pool-only micro-benchmark and --check; smoke.cpp single-threaded e2e test
    compare.hpp     token comparison; tests/ fork-server edge-case binaries + server_test
- tools/            Python 3.12 (stdlib + requirements.txt):
    build.py        builds everything into build/ (--force after header changes)
    run.py          experiment orchestrator (randomised blocks, resumable, git-stamped)
    flatten.py -> aggregate.py -> plots.py   raw JSON -> runs.csv -> summary.json -> charts
    results_table.py  README key-results table from summary.json
    sanity.py       plain gen/brute/fast check; tier_bugs.py measures planted-bug rates
    shrink.py, shrink_scaling.py, bug_gallery.py, repro.py   shrinking and bug gallery
    llm.py          Ollama explain/gen (random_api.txt is part of the gen prompt)
    problems.py     shared helpers (manifest, compile, run_test); style.py strategy colours
    selftest.sh     build + all self-tests, PASS/FAIL per item
- build/            compiled binaries (gitignored); build/plain/ = plain binaries for Python tools
- results/          run outputs (gitignored): raw/<experiment>/, runs.csv, summary.json, charts/,
                    bugs/ (gallery), llm/ (answers + prompts)
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
- Sizes are always clamped to max_size from fuzz_config.json.
- tests_to_bug = number of tests up to and including the first failing one (always >= 1).
- Dataset/bugs.json: one planted bug per problem with measured "rate" (% at sizes 5/20/max),
  "tier" (hard = all rates <= 15 %) and "kind"; regenerate with tools/tier_bugs.py.
  Note: suffixarray and number_of_substrings carry the same bug (shared SA-IS code).

## Design rules (do not change without being asked)
- A pool entry is a recipe (variant, size, seed) that reached new coverage, never raw
  input text. Mutation keeps the variant, perturbs size (clamped), draws a fresh seed.
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
- "hunt" is exploratory (30 repeats, all hard-tier problems); "hunt-focus" (100 repeats, 8 workers,
  the 3 hard-tier problems with the most tests-to-bug; constant FOCUS_PROBLEMS in tools/run.py,
  recorded in results/raw/hunt-focus/focus.json) is the confirmatory test with its own Holm family.
  Confirmatory problems (chosen by rule before data collection, commit date is the
  record): majority_voting, range_linear_add_range_min, longest_common_substring.
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
- tools/build.py only tracks each target's own source (plus fs_runtime.o and core headers for
  tools). After changing any other header (params.h, common/*.h, problem .hpp) run build.py --force.
- Do not add dependencies without asking (Python: requirements.txt; JS: dashboard/package.json).
- The repo path contains a space. Always call subprocess with argument lists, never
  shell strings; quote paths in any shell command.
