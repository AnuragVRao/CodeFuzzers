# CodeFuzzers
Parallel differential fuzzer for competitive-programming solutions. Course project:
code must be small, readable, and to the point. Prefer fewer files. No frameworks
beyond those listed here.

## Layout
- problems/<name>/  dataset (never modify unless explicitly asked)
- core/             C++17: fuzzer binary (worker threads, shared pool, 5 lock
                    strategies) and the forkserver + coverage runtime
- tools/            Python 3.12 scripts: build.py, run.py, shrink.py, aggregate.py, llm.py
- build/            compiled binaries (gitignored)
- results/          run outputs (gitignored)
- dashboard/        Vite + React + Recharts, reads results/summary.json, no backend

## Design rules (do not change without being asked)
- Pool entries are generator PARAMETERS (seed + size knobs), never raw input text.
  Mutation and shrinking change parameters, so generated inputs are always valid.
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
