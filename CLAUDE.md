# CodeFuzzers
Parallel differential fuzzer for competitive-programming solutions. Course project:
code must be small, readable, and to the point. Prefer fewer files. No frameworks
beyond those listed here.

## Layout
- Dataset/problems/<group>/<name>/  dataset; groups: arrays, graphs, strings.
  Shared headers in Dataset/common/. Problem list comes from Dataset/manifest.json.
  (never modify unless explicitly asked)
- fuzz_config.json  per-problem settings: {"<problem>": {"max_size": N}}
- core/             C++17: fuzzer binary (worker threads, shared pool, 5 lock
                    strategies) and the forkserver + coverage runtime
- tools/            Python 3.12 scripts: build.py, run.py, shrink.py, aggregate.py, llm.py
- build/            compiled binaries (gitignored)
- results/          run outputs (gitignored)
- dashboard/        Vite + React + Recharts, reads results/summary.json, no backend

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
  the 3 hard-tier problems with the most tests-to-bug, frozen in results/raw/hunt-focus/focus.json)
  is the confirmatory test with its own Holm family.

## Environment
WSL2 Ubuntu 24.04, 20 logical cores, g++ 13.3, Python 3.12.

## Working style
- Small steps. Do only what the current prompt asks; do not start the next step.
- End every step by running the test command given and showing its real output.
- tools/build.py only tracks each target's own source (plus fs_runtime.o and core headers for
  tools). After changing any other header (params.h, common/*.h, problem .hpp) run build.py --force.
- Do not add dependencies without asking.
- The repo path contains a space. Always call subprocess with argument lists, never
  shell strings; quote paths in any shell command.
