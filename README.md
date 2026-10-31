# CodeFuzzers

CodeFuzzers is a parallel differential fuzzer for competitive-programming solutions. For each of
30 problems from Library Checker it generates random valid inputs, runs a fast solution and a slow
brute-force reference on them, and reports any input where the two disagree. Many worker threads
fuzz at the same time and can share a pool of "recipes" (generator settings that reached new code
coverage). A shrinker reduces each failing input, and a dashboard shows the results.

The project asks three questions:

- **Systems:** what does it cost to share one recipe pool between worker threads, and how does the
  cost depend on the synchronisation strategy (one mutex, sharded mutexes, a readers-writer lock,
  copy-on-write snapshots) compared with workers that share nothing?
- **Algorithmic:** does coverage guidance, and in particular *shared* coverage guidance, find
  planted bugs in fewer tests than unguided random testing?
- **Steerable recipes:** if every random draw of the generator is recorded (a "tape") and single draws are mutated,
  are bugs found in fewer tests, and can the same tapes shrink failing inputs further? See
  [Tape recipes and the shrinker](#tape-recipes-and-the-shrinker).

## Pipeline

1. **Preparation.** Library Checker problems curated and bundled (generator, brute reference, fast
   solution, checker); lightweight and path-tracking builds. Every generator takes a seed and a size;
   each problem got one planted bug (`sol_bug.cpp`) whose trigger rate was measured.
2. **Control.** A Python orchestrator (`tools/run.py`) varies workers, strategy, read/write mix and
   seed; pins cores; repeats every run. Runs are executed one at a time in a randomised block order.
3. **Timed run.** Workers take a recipe from the shared pool, generate the test, run reference and
   fast solution, compare, and add recipes that reach new coverage. Solutions run through a
   fork-server, so a test costs a `fork()` instead of a full process start.
4. **Shrinking.** The tape shrinker (default of `tools/shrink.py`) shrinks the generator's random tape, then the
   input text (count-aware line deletion, then ddmin); every candidate is checked by the problem's verifier and a
   fresh run of reference and buggy solution. The faster generator-size shrinker (`--old`; parallel search over
   smaller sizes and fresh seeds) is used by the bug gallery and the analysis website.
5. **Aggregation.** Medians, IQRs and Mann–Whitney tests across workers, strategies and workloads;
   charts for speed-up, efficiency and time to bug. A local LLM (Ollama) explains shrunk failures and
   drafts generators, outside the timed region.

## Repository layout

```
Dataset/            30 problems (arrays, graphs, strings): generators, brute, sol, sol_bug, checker,
                    verifier, params.h; manifest.json; bugs.json (planted bugs, measured rates)
core/               C++17: fs_runtime.cpp (fork-server + coverage runtime), server.hpp (client),
                    pool.hpp (5 pool strategies), fuzzer.cpp, pool_bench.cpp, smoke.cpp, compare.hpp,
                    arena.hpp (tape arena), mutate.hpp (tape mutation), part2.cpp (mutation diagnostics),
                    tape_file_runtime.cpp (file-based tape sessions for the shrinker)
core/tests/         fork-server, checker and tape tests; golden_gen.json (golden generator hashes)
tools/              Python: build, run, flatten, aggregate, plots, results_table, sanity, tier_bugs,
                    shrink, shrink_scaling, bug_gallery, repro, llm, problems, style, golden_gen, part2,
                    fp_sim, pilot_report, pilot_posthoc, shrink_run, shrink_test, shrink_report(_s2),
                    shrink_replay_check, posthoc_misc; analysis website (server, analyze, e2e_test.sh);
                    selftest.sh
docs/               roadmap, tape design, pre-registered pilot plan, frozen shrinker plans, results
                    (v2_results.md, append-only), v2_key_numbers.md (where every headline number comes from)
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

Tape recipes and the shrinker (the shrinker evaluation reads the hunt and pilot runs in `results/raw/`):

```bash
python3 tools/golden_gen.py --check                    # generators unchanged without a tape session
python3 tools/part2.py                                 # pilot criterion (a), ~1 min
python3 tools/run.py --exp pilot --preset full         # pilot criterion (b), ~7 min
python3 tools/pilot_report.py && python3 tools/pilot_posthoc.py
python3 tools/shrink_run.py --set eval --shrinker new --jobs 8 --max-evals 10000 --wall 300 --out results/shrink/eval_s2   # S2, ~1.7 h
python3 tools/shrink_run.py --set eval --shrinker new --s1 --jobs 8 --max-evals 10000 --wall 300 --out results/shrink/eval # S1, ~1.8 h
python3 tools/shrink_run.py --set eval --shrinker old --jobs 16                                                            # ~12 min
python3 tools/shrink_report_s2.py && python3 tools/shrink_replay_check.py && python3 tools/posthoc_misc.py
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
| Generator-size shrinker (gallery bugs): median bytes kept / bugs re-validated | 19% / 30 of 30 |
| Generator-size shrinker speed-up at 20 worker processes (median over 3 problems) | 9.1× |
| LLM qwen2.5-coder:7b: bug line within ±3 (chance) / category (majority baseline) | 4/29 (7%, p = 0.133) / 9/29 (boundary / init 24%, p = 0.25) |
| LLM qwen2.5-coder:7b: generators compiled (first try + after repair) / mean verifier acceptance | 3 + 5 of 11 / 69% |
| LLM qwen3:8b: bug line within ±3 (chance) / category (majority baseline) | 7/29 (7%, p = 0.002) / 9/29 (boundary / init 24%, p = 0.25) |

In short: with a realistic workload (K=0, one pool read and write per test) sharing the pool costs
nothing measurable, whatever the strategy. Extra pool traffic separates the strategies: copy-on-write
snapshots collapse under write-heavy traffic exactly as the pool-only benchmark predicts, while the
mutex-based strategies stay close to noshare. The hunt experiments found no difference between
random, privately guided and shared-guided fuzzing; the tests could only have detected differences of
about 1.6× or more, and the planted bugs are found within a few hundred tests, before guidance has much
to work with. Steering the generator's draws (tape recipes) made bug finding slower, not faster, but the same tapes
give a shrinker that reduces failing inputs far more than shrinking the generator size (on two of the three focus
problems; on the third both reach the smallest known input). Only qwen3:8b located bugs better than chance.

## Tape recipes and the shrinker

This part followed a pre-registered plan (`docs/v2_roadmap.md`, `docs/v2_pilot_plan.md`, committed before any pilot
data). Every number below is listed with its source, script and data hashes in `docs/v2_key_numbers.md`; the full
results are in `docs/v2_results.md`.

**Tape recipes.** With a tape session active, every word the generator draws from `Random` is recorded; a tape recipe
is (variant, size, seed, tape), and replaying the tape reproduces the input byte for byte. Mutating single draws
changes the input locally instead of drawing a fresh seed. Without a session every generator produces exactly its
normal output (golden test: 740 hashes, three build flavours), so the scale and hunt experiments are unaffected.
Admitted tapes live in one append-only arena shared by the workers.

**Pilot.** Three arms: random-capture (the random strategy, recording tapes so that all arms run the same build),
tape-noshare and tape-rwlock; the 3 confirmatory focus problems; 8 workers, 20 s per run; 200 runs per arm and
problem. Continuing required (a) draw mutations that change the input locally and (b) a tape arm at ≤ 0.70× random's
median tests-to-bug on at least one problem.

| Pilot result | Value |
|---|---|
| (a) mutation locality, draw-level (changed input / median similarity) | 0.84–0.92 / 0.96–0.98 on all 3 problems: PASS |
| (b) median tests-to-bug, random-capture / tape-noshare / tape-rwlock, majority_voting | 319.5 / 1,238.5 / 1,135.5 |
| (b) same, range_linear_add_range_min | 196.0 / 1,041.5 / 1,206.5 |
| (b) same, longest_common_substring | 289.5 / 357.5 / 229.5 |
| (b) tape / random ratios (95% bootstrap CI, post-hoc) | 3.9× [3.0, 5.0], 3.6× [2.5, 5.1], 5.3× [4.1, 6.8], 6.2× [4.7, 7.9], 1.24× [0.93, 1.62], 0.79× [0.62, 0.98] |
| Verdict | **STOP**: (b) FAIL; the planned follow-ups (comparison-operand feedback, a confirmatory tape experiment) were cancelled |

Tape guidance needed 3.6–6.2× more tests on two of the three problems. In a post-hoc, model-based decomposition
(`docs/v2_results.md`, "Exploratory (post-hoc) analysis"), mutated children found the bug at about 0.06–0.20× the
rate of fresh random recipes on those two problems. Under no effect, the criterion would have given a false PROCEED
in 3.7–3.8% of pilots at n = 200 (`tools/fp_sim.py`).

**Shrinker.** The tape shrinker first shrinks the tape (truncate, delete words, zero and reduce draws), then the text:
a count-aware stage deletes query lines and decrements the counts in the first line to match, then line and token
ddmin. A candidate counts only if the verifier accepts it and it is still a wrong answer (WA). Two versions were
evaluated, each once under a frozen plan, on all 1,973 distinct failing inputs of the 3 focus problems (3,513 bugs
from the hunts, the pilot and the bug gallery): S1 without the count-aware stage, and the final S2 with it, against
the generator-size shrinker.

| Median tokens after shrinking (floor = smallest failing input found by hand) | majority_voting | range_linear_add_range_min | longest_common_substring |
|---|---:|---:|---:|
| before | 401 | 350 | 8 |
| generator-size shrinker | 378 | 187 | 3 |
| tape shrinker S1 (tape + ddmin) | 113 | 174 | 3 |
| tape shrinker S2 (tape + count-aware + ddmin, final) | 112 | 30 | 3 |
| floor | 69 | 11 | 3 |

S2 versus S1 on the same inputs: smaller on 922 of 941 range_linear_add_range_min inputs (median ratio 0.20) and 425 of
967 majority_voting inputs, never larger. All 1,973 final inputs of every shrinker reproduce the original wrong answer
on a cold replay (`tools/shrink_replay_check.py`). S2 was designed after S1's results were seen; it is the last
iteration by rule.

To shrink one bug: `python3 tools/shrink.py <problem> <bug-dir> --out <dir>` (tape shrinker);
`python3 tools/shrink.py --old <problem> <bug-dir>` (generator-size shrinker).

## Design decisions

- **Fork-server** — starting a process per test costs more than the test itself; a pre-forked server costs one `fork()`.
- **`-no-pie` coverage builds** — fixed code addresses give the same coverage IDs in every worker and every run.
- **Hit-count buckets** — with plain edge coverage the map saturated after a handful of tests and the pool stopped growing.
- **Recipes instead of raw inputs** — mutating (variant, size, seed) always yields a valid input; byte mutation would not.
- **Generator argument templates** — placeholders are whole argv tokens filled by the fork-server; backward-compatible, verified by cross-check and a paired A/B comparison against the previous build (10 alternating pairs, median ratio 1.002 [CI 0.968–1.035]).
- **Shrinking in generator space** — delta debugging on bytes breaks format-constrained inputs; shrinking the generator size, or its recorded draws, keeps them valid.
- **Verifier-checked text reduction** — after the tape stage, text steps are allowed only when the problem's verifier accepts the result and the failure is still a wrong answer.
- **Pre-registered kill criterion for tape recipes** — the pilot's PROCEED/STOP rule and its false-PROCEED rate were committed before data; the STOP verdict was followed.
- **Equal-work random recipes in scale runs** — guided recipes gave each strategy a different input-size mix (mean size 76–84 vs 100), confounding throughput.
- **Randomised block run order** — with strategies run one after another, slow machine drift made sharing look up to 18% faster than no sharing; interleaving removed it.
- **Weak scaling (2500 tests per worker)** — fixed totals made 20-worker runs shorter than a second, too short to measure reliably.
- **Censoring-aware medians** — a hunt without a bug counts as +∞, so medians are never biased by dropping slow runs.
- **Holm correction** — 66 exploratory comparisons would produce false positives without it.
- **Pre-declared confirmatory hunt** — the three problems were fixed by rule and committed before their data was collected.

## Website

Upload your own solution and get a differential-fuzzing report: build, validation, size calibration, a performance
section, a time-boxed hunt, shrinking of the failing test, an optional LLM explanation.

**Start** (two processes, both bound to localhost only):

```bash
python3 tools/server.py                                   # analysis server, 127.0.0.1:8000
cd dashboard && source ~/.nvm/nvm.sh && npm run dev       # dashboard, http://localhost:5173 -> Analyze tab
```

**Inputs** — four files, at most 1 MB each, UTF-8 C++:
- `gen.cpp` generator, `ref.cpp` reference (brute force), `sol.cpp` solution under test, and `checker.cpp` (testlib) when
  the checker mode is "custom"; otherwise outputs are compared token by token.
- Files must be self-contained. `testlib.h`, `random.h` and `fastio.h` are available as headers.
- The generator takes its arguments from a template of whole arguments: `{seed} {size}` (default), `{seed}` (seed only) or
  e.g. `-seed {seed} -n {size}`. `{seed}` and `{size}` must be whole arguments (`-n {size}`, not `-n={size}`).
- The generator must be deterministic for a fixed seed (checked at validation; a generator seeded from `std::random_device`
  is rejected). A generator exiting non-zero means "skip this seed".

**Budget** — 1, 3 or 10 minutes. It covers building, validation, calibration, the performance measurements and the hunt
(the hunt gets whatever remains, minus 3 s); shrinking may exceed it by up to ~8 s if a bug is found at the very end.
The optional LLM explanation runs after the budget (typically 15–30 s). The whole job is killed after budget + 120 s.

**Report sections** — verdict banner; failing test (shrunk input, reference and solution output, differing tokens
highlighted) and the unverified LLM suggestion with the surrounding source lines; calibration (reference time per input vs
generator size, p75 of 9 inputs, the size cap at 50 ms); performance (speed-up vs workers, noshare vs rwlock, sizes 1–200);
hunt statistics. `report.json` can be downloaded.

**Clean bound** — if no failing input is found in N tests, the report says that with 95 % confidence fewer than
1 − 0.05^(1/N) of the inputs expose a bug. "Inputs" means inputs from this generator with sizes drawn log-uniformly from
1–max_size (the hunt's size distribution); it is not a statement about other generators or sizes.

**Seed-only mode** — if the template has no `{size}` (or the output does not grow with it), calibration, guided size
mutation and size shrinking are disabled. Shrinking then only keeps the smallest failing input among fresh seeds, which
shrinks far less: on the same bug (`range_affine_point_get`) the sized generator shrinks the failing input from 899 to
43 bytes, the seed-only generator from 13842 to 6227 bytes. Give the generator a size knob when you can.

**Guard rails** — one job at a time (FIFO queue), each in its own process group with limits (4 GiB address space, 256 MiB
files, no core dumps, 4096 processes); cancel, wall-limit timeout and a final kill of the group after every job; uploaded
code that forks ends with "Process limit reached". These are resource limits, not a sandbox: the server runs uploaded C++
with your user's permissions, so it binds to 127.0.0.1 only and must not be exposed to a network. Tests:
`tools/e2e_test.sh` (full, ~5 min) and the fast subset inside `tools/selftest.sh`.

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
- **Post-hoc analyses.** The explanation of the pilot result and the S2 shrinker were developed after the
  pre-registered results were seen; they are labelled post-hoc.
- **One build per comparison.** All scaling numbers come from one build (runs listed under *Key results*); throughput
  checks made after the tape code was added were regression gates and are not mixed into the scaling results.
- **Shrinker floors.** The floors are the smallest failing inputs found by hand, not proven minima.

## Limitations and future work

- Larger inputs and bugs that need more than a few hundred tests, so that guidance can matter.
- Real (historical) bugs from contest submissions instead of planted ones.
- Bare-metal Linux measurements to remove the WSL2 virtualisation layer.
- A lock-free pool (e.g. per-worker buffers merged in batches) as a sixth strategy.
- Repeated LLM runs with several seeds and a larger problem set.
- Shrinker: renumber indices inside body lines, so the number of elements can fall below the largest index a surviving
  query refers to (the S2 plan predicts this keeps range_linear_add_range_min above its floor); handle outputs whose
  token count changes (one development bug, lyndon_factorization, ends as a presentation error and is left
  unshrunk).
