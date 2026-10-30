# Known issues (v1)

Left unchanged so v1 results stay comparable. None affects a focus problem's bug detection.

1. **static_range_lis_query truncates its seed.** `Dataset/problems/arrays/static_range_lis_query/gen/generator.cpp:9`
   stores `atoll(argv[1])` in an `int`. Output is still deterministic, but distinct 63-bit seeds collide far
   more often than in other generators. Not a focus problem.

2. **`tests` vs `tests_before` with workers in flight.** In the per-run JSON, `tests` sums each worker's
   *started* tests, including those still running when a hunt stops. `first_bug.tests_before` is the global
   *completed* counter when the bug is recorded (`core/fuzzer.cpp:88`), so it counts other workers' finished
   tests and excludes tests in flight. With 8 workers the two differ by up to about 8 (e.g. 1171 vs 1159).
   Analysis uses `tests_to_bug = tests_before + 1` (`tools/aggregate.py:12`).

3. **The shrinker returned unchanged inputs for two focus bugs.** In `results/bugs/gallery.json`,
   majority_voting (2795 bytes, 161 lines) and range_linear_add_range_min (135 bytes, 8 lines) have
   `shrunk` identical to `original` (same size, seed and bytes). Recipe-level shrinking found no smaller
   recipe that still fails. Step S of docs/v2_roadmap.md addresses this.

4. **Stale `bug_dir` in hunt-quick runs.** `config.bug_dir` in `results/raw/hunt-quick/**/*.json` points
   to `results/raw/hunt/...`; the runs were moved afterwards, and the full hunt later reused those paths.
   The correct saved input is the run's sibling directory (`<run>.json` -> `<run>/input.txt`).
   Found while replaying v1 first bugs (Step 0.2); with the sibling path all 3,888 saved inputs match
   their regenerated recipes byte for byte.
