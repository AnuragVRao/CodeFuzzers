# CodeFuzzers

CodeFuzzers is a parallel differential fuzzer for competitive-programming solutions. For each of
30 problems from Library Checker it generates random valid inputs, runs a fast solution and a slow
brute-force reference on them, and reports any input where the two disagree. Many worker threads
fuzz at the same time and can share a pool of "recipes" (generator settings that reached new code
coverage). A parallel shrinker reduces each failing input, and a dashboard shows the results.

The project asks two questions:

- **Systems:** what does it cost to share one recipe pool between worker threads, and how does the
  cost depend on the synchronisation strategy (one mutex, sharded mutexes, a readers-writer lock,
  copy-on-write snapshots) compared with workers that share nothing?
- **Algorithmic:** does coverage guidance, and in particular *shared* coverage guidance, find
  planted bugs in fewer tests than unguided random testing?

## Pipeline

1. **Preparation.** Library Checker problems curated and bundled (generator, brute reference, fast
   solution, checker); lightweight and path-tracking builds. Every generator takes a seed and a size;
   each problem got one planted bug (`sol_bug.cpp`) whose trigger rate was measured.
2. **Control.** A Python orchestrator (`tools/run.py`) varies workers, strategy, read/write mix and
   seed; pins cores; repeats every run. Runs are executed one at a time in a randomised block order.
3. **Timed run.** Workers take a recipe from the shared pool, generate the test, run reference and
   fast solution, compare, and add recipes that reach new coverage. Solutions run through a
   fork-server, so a test costs a `fork()` instead of a full process start.
4. **Shrinking.** Parallel generator-space shrinking finds the smallest input that still fails, then
   re-validates it with the problem's verifier and a fresh run of reference and buggy solution.
5. **Aggregation.** Medians, IQRs and Mann–Whitney tests across workers, strategies and workloads;
   charts for speed-up, efficiency and time to bug. A local LLM (Ollama) explains shrunk failures and
   drafts generators, outside the timed region.

## Repository layout

```
Dataset/            30 problems (arrays, graphs, strings): generators, brute, sol, sol_bug, checker,
                    verifier, params.h; manifest.json; bugs.json (planted bugs, measured rates)
core/               C++17: fs_runtime.cpp (fork-server + coverage runtime), server.hpp (client),
                    pool.hpp (5 pool strategies), fuzzer.cpp, pool_bench.cpp, smoke.cpp, compare.hpp
core/tests/         fork-server edge-case programs and server_test
tools/              Python: build, run, flatten, aggregate, plots, results_table, sanity, tier_bugs,
                    shrink, shrink_scaling, bug_gallery, repro, llm, problems, style; selftest.sh
dashboard/          Vite + React + Recharts; reads results/summary.json (no backend)
fuzz_config.json    max input size per problem
requirements.txt    Python packages (numpy, scipy, matplotlib)
build/, results/    generated (gitignored): binaries; raw runs, runs.csv, summary.json, charts, bugs, llm
```

`CLAUDE.md` is the developer documentation: conventions, design rules and every file's role.

## Requirements

- Windows with **WSL2, Ubuntu 24.04**, **g++ 13**, **Python 3.12**
- `pip install --break-system-packages -r requirements.txt`
- **Node 22** for the dashboard (version in `dashboard/.nvmrc`), installed with nvm; run
  `source ~/.nvm/nvm.sh` in each shell before `npm`
- Optional: **Ollama** with `qwen2.5-coder:7b` (and optionally `qwen3:8b`). If Ollama runs on
  Windows, enable `networkingMode=mirrored` in `.wslconfig` so it is reachable at
  `http://localhost:11434`, or set `OLLAMA_URL`.

## Quick start (about 10 minutes)

```bash
python3 tools/build.py                        # ~30 s, builds everything into build/
tools/selftest.sh                             # ~20 s, prints PASS/FAIL per check
python3 tools/run.py --exp scale --preset quick
python3 tools/run.py --exp hunt --preset quick
python3 tools/run.py --exp pinning --preset full
python3 tools/bug_gallery.py                  # hunt + shrink one bug per problem (~1 min)
python3 tools/flatten.py && python3 tools/aggregate.py && python3 tools/plots.py
cd dashboard && source ~/.nvm/nvm.sh && npm install && npm run dev   # open http://localhost:5173
```

The quick presets are small; the dashboard marks them as preliminary. Charts are written to
`results/charts/`.

## Full reproduction

Prepare the laptop first:

- plugged in, Windows power mode **Best performance**;
- sleep **Never** on power, lid close action **Do nothing** (a suspension pauses the virtual machine and
  corrupts the run in progress, see *Threats to validity*);
- close other applications, pause Windows Update, no other WSL jobs;
- start long jobs with `nohup … & disown` so they survive the terminal closing.

```bash
python3 tools/build.py && tools/selftest.sh
nohup bash -c '
  python3 tools/run.py --exp hunt --preset full &&          # ~8 min, 2970 runs (exploratory)
  python3 tools/run.py --exp hunt-focus --preset full &&    # ~3 min, 900 runs (confirmatory)
  python3 tools/run.py --exp scale --preset full &&         # ~80 min, 1800 runs
  python3 tools/run.py --exp pinning --preset full          # ~1 min, 10 runs
' > results/rerun.log 2>&1 & disown
tail -f results/rerun.log
```

Then, outside the timed experiments:

```bash
python3 tools/bug_gallery.py          # ~1 min
python3 tools/shrink_scaling.py       # ~3 min
python3 tools/llm.py explain --model qwen2.5-coder:7b   # ~5 min (optional, needs Ollama)
python3 tools/llm.py explain --model qwen3:8b           # ~10 min
python3 tools/llm.py gen --model qwen2.5-coder:7b       # ~6 min
python3 tools/flatten.py && python3 tools/aggregate.py && python3 tools/plots.py
python3 tools/results_table.py
```

`run.py --dry-run` prints the plan and an ETA. Runs are resumable: finished result files are
skipped. The confirmatory problems are the constant `FOCUS_PROBLEMS` in `tools/run.py`, fixed before
data collection; each hunt-focus run records them in `results/raw/hunt-focus/focus.json`.

## Key results

Machine: i7-13650HX laptop, WSL2. Table printed by `python3 tools/results_table.py`; runs from
commits `078b143` (scale, pinning, hunt-focus) and `672be82` (exploratory hunt; the only later code
change is the run order in `run.py`).

| Result | Value |
|---|---|
| Speed-up of noshare at 20 workers, range_add_range_min (weak scaling, vs 1 worker) | 8.72× |
| Speed-up of noshare at 20 workers, vertex_add_path_sum (weak scaling, vs 1 worker) | 8.97× |
| Speed-up of noshare at 20 workers, zalgorithm (weak scaling, vs 1 worker) | 8.58× |
| Sharing strategies vs noshare at K=0 (all problems, 2–20 workers) | 0.953 – 1.052 |
| rwlock vs noshare at 20 workers, K=50/F=0.1 (range over problems) | 0.88 – 0.91 |
| rwlock vs noshare at 20 workers, K=50/F=0.5 (range over problems) | 0.91 – 0.99 |
| snapshot vs noshare at 20 workers, K=50/F=0.1 (range over problems) | 0.86 – 0.89 |
| snapshot vs noshare at 20 workers, K=50/F=0.5 (range over problems) | 0.35 – 0.41 |
| snapshot at K=50/F=0.5, 20 workers: measured vs predicted tests/s (pool_bench ceiling) | range_add_range_min 5333 vs 5170, vertex_add_path_sum 4930 vs 5170, zalgorithm 5382 vs 5170 |
| CPU pinning gain (global, 8 workers, median of 5) | +52% (10021 vs 6577 tests/s) |
| Confirmatory hunt, longest_common_substring: noshare / random median tests-to-bug (8 workers, n=100) | 0.61 [95% CI 0.41–1.01], p_Holm = 0.47 |
| Confirmatory hunt, longest_common_substring: rwlock / noshare median tests-to-bug (8 workers, n=100) | 0.94 [95% CI 0.55–1.31], p_Holm = 1.00 |
| Confirmatory hunt, majority_voting: noshare / random median tests-to-bug (8 workers, n=100) | 1.03 [95% CI 0.67–1.67], p_Holm = 1.00 |
| Confirmatory hunt, majority_voting: rwlock / noshare median tests-to-bug (8 workers, n=100) | 1.19 [95% CI 0.73–1.83], p_Holm = 1.00 |
| Confirmatory hunt, range_linear_add_range_min: noshare / random median tests-to-bug (8 workers, n=100) | 0.88 [95% CI 0.52–1.48], p_Holm = 1.00 |
| Confirmatory hunt, range_linear_add_range_min: rwlock / noshare median tests-to-bug (8 workers, n=100) | 1.10 [95% CI 0.73–1.93], p_Holm = 1.00 |
| Exploratory hunt comparisons with p_Holm < 0.05 | 0 of 66 |
| Minimum detectable median ratio (Mann–Whitney, 80% power) | n=30: 2.5×, n=100: 1.6× |
| Shrinker: median bytes kept / bugs re-validated | 19% / 30 of 30 |
| Shrinker speed-up at 20 worker processes (median over 3 problems) | 9.1× |
| LLM qwen2.5-coder:7b: bug line within ±3 (chance) / category (majority baseline) | 4/29 (7%, p = 0.133) / 9/29 (boundary / init 24%, p = 0.25) |
| LLM qwen2.5-coder:7b: generators compiled (first try + after repair) / mean verifier acceptance | 3 + 5 of 11 / 69% |
| LLM qwen3:8b: bug line within ±3 (chance) / category (majority baseline) | 7/29 (7%, p = 0.002) / 9/29 (boundary / init 24%, p = 0.25) |

In short: with a realistic workload (K=0, one pool read and write per test) sharing the pool costs
nothing measurable, whatever the strategy. Extra pool traffic separates the strategies: copy-on-write
snapshots collapse under write-heavy traffic exactly as the pool-only benchmark predicts, while the
mutex-based strategies stay close to noshare. The hunt experiments found no difference between
random, privately guided and shared-guided fuzzing; the tests could only have detected differences of
about 1.6× or more, and the planted bugs are found within a few hundred tests, before guidance has much
to work with. Only qwen3:8b located bugs better than chance.

## Design decisions

- **Fork-server** — starting a process per test costs more than the test itself; a pre-forked server costs one `fork()`.
- **`-no-pie` coverage builds** — fixed code addresses give the same coverage IDs in every worker and every run.
- **Hit-count buckets** — with plain edge coverage the map saturated after a handful of tests and the pool stopped growing.
- **Recipes instead of raw inputs** — mutating (variant, size, seed) always yields a valid input; byte mutation would not.
- **Generator argument templates (v1.1)** — placeholders are whole argv tokens filled by the fork-server; backward-compatible, verified by cross-check and a paired A/B comparison against the previous build (10 alternating pairs, median ratio 1.002 [CI 0.968–1.035]).
- **Generator-space shrinking** — delta debugging on bytes breaks format-constrained inputs; shrinking the generator size keeps them valid.
- **Equal-work random recipes in scale runs** — guided recipes gave each strategy a different input-size mix (mean size 76–84 vs 100), confounding throughput.
- **Randomised block run order** — with strategies run one after another, slow machine drift made sharing look up to 18% faster than no sharing; interleaving removed it.
- **Weak scaling (2500 tests per worker)** — fixed totals made 20-worker runs shorter than a second, too short to measure reliably.
- **Censoring-aware medians** — a hunt without a bug counts as +∞, so medians are never biased by dropping slow runs.
- **Holm correction** — 66 exploratory comparisons would produce false positives without it.
- **Pre-declared confirmatory hunt** — the three problems were fixed by rule and committed before their data was collected.

## Threats to validity

- **CPU topology.** The i7-13650HX is a hybrid chip (6 performance cores with hyper-threading, 8
  efficiency cores); WSL2 presents it as 10 cores × 2 threads. "One thread per core first" pinning
  is based on that virtual topology, and part of the sub-linear speed-up (8.6–9.0× at 20 workers)
  comes from hyper-threads and slower cores rather than from the fuzzer.
- **Laptop measurement noise.** Run-to-run spread is about 2% (median IQR/median), up to 10%.
  Results within ±5% of each other are treated as equal.
- **Suspension during the scale run.** The laptop slept for 60 minutes mid-run. Based on that event
  (not on their values), the two runs adjacent to the gap were deleted and re-run; all other
  runs were kept.
- **Planted bugs.** The bugs were written by an AI coding assistant (Claude Opus 5.5, per the
  co-author line of commit `9628a09`) and calibrated to a target trigger-rate window, so they form a
  selected benchmark, not a sample of real mistakes. suffixarray and number_of_substrings share one
  bug through shared SA-IS code.
- **Hard-tier selection.** Hunt comparisons use only the 11 bugs that trigger in ≤ 15% of tests at
  every size; easier bugs are found almost immediately by any strategy.
- **Small inputs.** Sizes are capped at 200 (100 for two graph problems), so the bugs and the coverage
  space are small.
- **LLM evaluation.** One run per model at temperature 0.2 and a fixed seed, on 29 problems; the
  numbers are indicative, not a benchmark.

## Limitations and future work

- Larger inputs and bugs that need more than a few hundred tests, so that guidance can matter.
- Real (historical) bugs from contest submissions instead of planted ones.
- Bare-metal Linux measurements to remove the WSL2 virtualisation layer.
- A lock-free pool (e.g. per-worker buffers merged in batches) as a sixth strategy.
- Repeated LLM runs with several seeds and a larger problem set.
