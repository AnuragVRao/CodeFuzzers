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
  64 KiB edge bitmap in shared memory.
- Timed region = worker loop only. Build, shrink, aggregation, and LLM calls are outside it.
- Two modes: "scale" (fixed test count, never stops early) and "hunt" (all workers
  stop on the first mismatch).
- Optional knob: extra pool reads/writes per test, to make lock contention measurable.

## Environment
WSL2 Ubuntu 24.04, 20 logical cores, g++ 13.3, Python 3.12.

## Working style
- Small steps. Do only what the current prompt asks; do not start the next step.
- End every step by running the test command given and showing its real output.
- Do not add dependencies without asking.
- The repo path contains a space. Always call subprocess with argument lists, never
  shell strings; quote paths in any shell command.
