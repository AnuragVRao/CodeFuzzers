# CodeFuzzers v2 roadmap (master plan)

This file is the single source of truth for the v2 work. Claude Code: read this file and CLAUDE.md at the start of EVERY session before doing anything.

## How to work with this roadmap

- Execute ONE step only, and only when the user says "Do Step X". Never start the next step on your own.
- Before coding a step: re-read that step's section and CLAUDE.md, then state your plan in at most 8 bullets.
- After a step: report in the step's OUTPUT format, update the Status table below (status + commit hash only), commit, then STOP and wait.
- Small steps: tools/selftest.sh must pass before every commit. One commit per task inside a step. No dependencies beyond those already in requirements.txt (C++ standard library for C++).
- If any verification fails: STOP and report the failure. Do not work around it.

## Integrity rules (never break these)

1. Never weaken, skip, or edit a test, threshold, or verification to make it pass.
2. Never modify anything under results/raw/ from v1 experiments.
3. The confirmatory focus set (majority_voting, range_linear_add_range_min, longest_common_substring) is frozen.
4. Pre-registration documents (docs/v2_pilot_plan.md, docs/v2_prereg.md) are never edited after their commit. Changes go in a dated "Amendment" section appended at the end, and must be reported to the user.
5. Never run extra experiment configurations beyond what a step specifies.
6. Scale experiments (--recipes random) must keep identical behaviour and pool cost to v1.
7. With no tape session active, every generator must produce byte-identical output to v1 (tools/golden_gen.py --check, from Step 0 onward).

## Status

| Step | Title | Status | Commit |
|---|---|---|---|
| 0 | Groundwork: golden test, ref_fail/checker_error outcomes, CLAUDE.md fixes, known issues | done | 714e5f4 |
| 2.0 | Feasibility check + tape design spec | done | 07509ce |
| 2a | Tape session support in random.h | done | f68a33f |
| 2b | Shared memory to generator fork-server | done | 95b5753 |
| 2c | Tape arena + pool entry handles | done | 1bc0350 |
| 2d | Tape mutation, dedup, metrics, arms | done | 0dbb9f8 |
| 2e | Mutation diagnostics + pre-declared pilot (PROCEED/STOP) | todo | |
| S | Shrinker: tape shrinking + verifier-checked text ddmin | todo | |
| 3 | trace-cmp value profile (only if 2e = PROCEED) | todo | |
| 4 | v2 confirmatory pre-registration + runs (only if 2e = PROCEED) | todo | |

There is no Step 1; the original groundwork prompt became Step 0.

Terminology: "random strategy" = --strategy random (no pool, no guidance; the v1 baseline arm). "--recipes random" = the recipe mode used by scale experiments (every strategy picks from its pool but ignores the pick). These are never abbreviated to a bare "random".

## Background (why this exists)

- v1 result: random strategy, private-guided (noshare) and shared-guided arms find planted bugs equally fast. Every confirmatory Holm p >= 0.47.
- Cause 1, no steering: every mutation draws a fresh seed (core/fuzzer.cpp:169), so a child input is unrelated to its parent. A pool entry only passes on (variant, size). "Sharing the corpus" in v1 = sharing a size distribution.
- Cause 2, no value signal: coverage is trace-pc with hit-count buckets. It cannot see a value approaching a threshold.
- Cause 3, shallow bugs: the random strategy finds the focus bugs at median 241-430 tests, 0.03-0.21 s per run.
- random.h facts: all generators draw only via Random. next(upper) masks to the next power of two, and rejects values > upper unless upper+1 is a power of two (no modulo). uniform_pair, choice and rejection loops are unbounded. 37 generator binaries for 30 problems.
- Focus bugs:
  - majority_voting: Fenwick off-by-one (sol_bug.cpp:79). Needs a value with > 64 occurrences plus a full-prefix query. No useful value signal expected.
  - range_linear_add_range_min: sentinel 1e9 instead of INF via chmin (sol_bug.cpp:116). Needs one value > 1e9 in a length-1 query. trace-cmp can see this comparison.
  - longest_common_substring: ans = -1 instead of 0 (sol_bug.cpp:141). Needs S and T to share no character (alphabet {a,b}), so small sizes help.
- The focus set was chosen by a difficulty rule AFTER the exploratory hunt and BEFORE confirmatory runs.
- Team decision: the "never modify Dataset" rule is relaxed for random.h tape support, subject to the golden test.

---

## Step 0: Groundwork

Scope: no changes to random.h, mutation logic, or pool.hpp.

Task 0.1 Golden generator test (do FIRST, on current HEAD)
- tools/golden_gen.py: for every generator binary (gen and gen_alt where present), seeds {1, 2, 3, 12345, 987654321} x sizes {1, 5, 50, 200}, record sha256 of stdout into core/tests/golden_gen.json with keys "<problem>/<binary>/<seed>/<size>".
- --check mode recomputes, prints every mismatch, exits non-zero on any.
- Add `python3 tools/golden_gen.py --check` to tools/selftest.sh.
- Verify: --check passes twice; report the number of entries.

Task 0.2 Checker _fail outcome
- FIRST report only, by REPLAY (the raw JSON does not store the checker's exit code; core/fuzzer.cpp:187 maps every non-OK checker result to "WA"): for every v1 run in results/raw/**/*.json with a first_bug, regenerate the input from (variant, size, seed) with the build/plain/ generator, run ref and fast, run the checker, and record its exit code. Report counts per problem per experiment. STOP and show the counts; wait for the user before changing core/fuzzer.cpp.
- Then, outcome mapping going forward (core/fuzzer.cpp around :187): testlib exit 3 (_fail) -> "ref_fail"; checker crash or any non-testlib exit code -> "checker_error"; WA and PE remain "WA". Neither ref_fail nor checker_error triggers first_bug. Add both to the outcomes JSON and tools/flatten.py.

Task 0.3 CLAUDE.md corrections (team-approved)
- Replace "Confirmatory problems (chosen by rule before data collection, commit date is the record)" with: "Confirmatory problems: chosen by a difficulty rule (largest median tests-to-bug over all three strategies) AFTER the exploratory hunt finished (hunt_full.log 2026-10-21 18:22 UTC; rule committed f2392e3 18:44 UTC), and BEFORE confirmatory (hunt-focus) data collection."
- In the Dataset rule add: "Exception (team-approved): Dataset/common/random.h may be modified for random-tape support, provided tools/golden_gen.py --check passes when no tape is supplied."
- Add near the top: "v2 work follows docs/v2_roadmap.md. Read it before any v2 task."
- Change no other rule.

Task 0.4 docs/known_issues.md (no code change)
- static_range_lis_query/gen/generator.cpp:9 truncates the seed to int (deterministic, collision-prone; not a focus problem; left unchanged for v1 comparability).
- tests vs tests_before semantics with 8 workers in flight; analysis uses tests_before + 1.
- The shrinker returned unchanged inputs for majority_voting and range_linear_add_range_min.

OUTPUT: per task: files changed, commit hash, verification command + output. Task 0.2 count reported before implementing.

---

## Step 2.0: Feasibility check + tape design spec

Part 1, report only (file:line evidence):
- F1. Is core/fs_runtime.cpp (or another runtime object) linked into the generator binaries, not only fast_sol/fast_bug? Show build.py lines.
- F2. How many Random instances does each generator construct? List any generator with more than one, or one constructed inside a loop.
- F3. Does any generator use Random before reading argv (global/static Random)?
- F4. How does the fork-server receive per-test generator arguments, and what IPC exists between worker and generator server?
- F5. Max raw next() calls for connected_components_of_complement_graph at the max hunt size: use an instrumented COPY of random.h in /tmp; do not modify the repo.
- STOP and wait if F1 is "no" or F2 finds a Random constructed inside a loop.

Part 2: write docs/tape_design.md with the content of the "Tape design spec" section at the end of this roadmap (fill CAP/LOGCAP from F5 with 2x headroom).

Part 3: in CLAUDE.md, under the pool-entry rule, add: "v2 (tape) recipes follow docs/tape_design.md. The v1 rule stays in force for all v1 experiments and all scale experiments."

OUTPUT: F1-F5 answers with evidence, commit hash.

---

## Step 2a: Tape session support in random.h

Scope: Dataset/common/random.h, the session-pointer definition in core/fs_runtime.cpp, new files under core/tests/ (built per tools/build.py into build/tests/). Nothing else.

Requirements:
1. Session pointer: DEFINED (strong symbol) in core/fs_runtime.cpp (and, from Step S, also in core/tape_file_runtime.cpp). random.h declares it as a weak extern and checks the symbol's address before dereferencing, so binaries without a runtime (build/plain/) behave exactly as v1. Null pointer (or absent symbol) means exact v1 behaviour (one predictable branch per next()). global_gen stays unchanged.
2. Raw next(): next input-tape word if any remain, else the instance's own xoshiro; append every returned word to the output tape; enforce the budget (set flag, _exit with a dedicated code).
3. next(upper): log (index of the ACCEPTED word, upper), accepted word only.
4. Session flag fallback_zero (used by Step S): past the end of the input tape, return 0 instead of xoshiro. Budget still applies.
5. Do not change any distribution logic (mask + reject stays exactly as is).

Tests (core/tests/tape_test.cpp -> build/tests/tape_test, new selftest step):
- T1. Golden --check passes after build.py --force.
- T2. Capture == v1: 3 real generators (one per group) x 5 seeds: active session with EMPTY input tape gives output identical to no session.
- T3. Replay: feeding the captured output tape back (any seed) reproduces identical output, consuming exactly len(tape) words, no fallback.
- T4. Local mutation: toy generator printing 20 x uniform(0, 1000); change draw 7 via its logged accepted word; output differs in exactly line 7; output tape length unchanged.
- T5. No shift through rejection: as T4 but pick a seed where draw 7 needed >= 1 rejection; lines 8-20 unchanged.
- T6. Budget: all-zero input tape with fallback_zero on a toy generator calling uniform_pair(0, 5) exits with the budget code within 1 s.

OUTPUT: diff summary, each test command + result, commit hash. If T1 fails, stop and report the first mismatch.

---

## Step 2b: Shared memory to the generator fork-server

Scope: core/fs_runtime.cpp and its server side, the worker-side client in core/, tools/build.py only if linkage requires it. No mutation or pool changes. All existing --recipes modes unchanged.

Requirements:
1. Reuse the existing coverage-memfd pattern (fd 197 for the fast binary, core/server.hpp start(), core/fuzzer.cpp:141-142): when tape mode is enabled, the GENERATOR server receives a tape memfd on fd 196, mapped by the worker and by the forked child. Extend the Request struct (core/fs_runtime.cpp:27) with tape fields (arm flag, in_len, fallback_zero, budget); the child arms the session pointer before main() only when the arm flag is set. Without tape mode, nothing about the generator server changes.
2. Worker API: run_gen_with_tape(variant, size, seed, const uint64_t* in, size_t in_len, bool fallback_zero) -> {stdout, status, out-tape span, draw-log span, flags}. Spans point into shm; callers copy what they keep.
3. Calls without a tape must leave the child's session pointer null.
4. Worker threads never call fork().

Tests:
- T1. Golden check + selftest pass.
- T2. Through the real fork-server: capture (empty input, seed S) then replay; stdout identical; repeat 1000 times on one problem with no shm/fd leaks (fd count of the worker and server processes before/after (via /proc/<pid>/fd)).
- T3. The budget exit code is reported as a distinct status, not a crash.
- T4. Overhead: scale config on majority_voting, --recipes random, fixed 10,000 tests, --strategy rwlock, 8 workers, 10 repeats, before (git worktree) vs after. Spread = min-max range of the "before" repeats. STOP if the after-median tests_per_sec differs from the before-median by more than 5% AND lies outside the before min-max range.

OUTPUT: diff summary, test results, T4 numbers, commit hash.

---

## Step 2c: Tape arena + pool entry handles

Scope: core/pool.hpp, new core/arena.hpp, minimal fuzzer.cpp changes to store handles. No mutation operators.

Requirements:
1. Arena: mmap-reserved region (default 1 GiB, configurable), atomic bump allocation, holds tape words + draw logs; a handle is published under the pool lock only after its copy completes; never freed or modified during a run.
2. Handle: arena offset, word count, draw count, input hash.
3. Scale experiments must keep sizeof(v1 Entry) and v1 Snapshot copy cost (e.g. template the pool on the entry type, or a separate tape entry type). Document the choice in a comment and in docs/tape_design.md.
4. Arena full: skip admission, count arena_full.
5. Mention the arena in CLAUDE.md design rules without changing v1 rules.
6. Report peak arena_bytes per run in the JSON.

Tests:
- T1. Golden check + selftest pass.
- T2. Scale benchmark on range_add_range_min, --recipes random, 2,500 tests per worker, K=50, F=0.5, pinned workers: all 5 lock strategies x {1, 8, 20} workers x 5 repeats, before (git worktree) vs after. Report median tests_per_sec per cell, percent change, and spread (= min-max range of the "before" repeats). STOP if in any cell the after-median differs from the before-median by more than 5% AND lies outside the before min-max range.
- T3. Stress test: 20 threads admitting and picking tape entries for 10 s under rwlock and sharded; every picked tape hashes to its recorded hash. Run once under -fsanitize=thread.

OUTPUT: diff summary, T2 table, T3 result incl. TSan output, commit hash.

---

## Step 2d: Tape mutation, dedup, metrics, arms

Scope: core/fuzzer.cpp, tools/run.py (new arms), tools/flatten.py and tools/aggregate.py (new metric columns only; existing statistics unchanged).

Requirements:
1. --recipes tape with operator probabilities exactly per the spec; --tape-span ablation flag; --tape-mut byte diagnostic mode.
2. Tests with no parent still run through a tape session (so their tape can be admitted); output must equal v1's for the same seed.
3. Dedup per the spec; skipped tests count as generated, not executed. Tests with no parent compare only against the per-worker recent-hash set.
4. All spec metrics in the per-run JSON and flattened CSV (mut_similarity is offline only, see Step 2e Part 2).
5. New arms in run.py: tape-noshare, tape-rwlock, tape-rwlock-span. Existing arms (random strategy, noshare, rwlock, ...) unchanged.
6. Draw writes replace the WHOLE accepted word with v (high bits zero); a draw's value is always read as word & mask(upper).
7. Copy op: if val(d1) > upper_d2, retry choosing d2 up to 4 times, then fall back to a value op; record the op actually applied (for T3's per-operator fractions).

Tests:
- T1. Golden check + selftest pass.
- T2. Determinism: 50 admitted entries from a short tape-rwlock run; regenerating from the stored (variant, size, seed, tape) reproduces the stored input hash.
- T3. Operator sanity on majority_voting: 10,000 mutated children; fraction per operator actually applied and mut_changed_input per operator.
- T4. Smoke: one run per new arm on each focus problem; all finish, bugs found; report budget/overflow counters.

OUTPUT: diff summary, test results, T3 table, commit hash.

---

## Step 2e: Diagnostics + pre-declared pilot

Part 1. Write docs/v2_pilot_plan.md with the content below, SHOW IT TO THE USER, and commit only after the user confirms the kill criterion (they may change the numbers before the commit, never after). Print commit hash + timestamp. Do not run anything before this commit.
- Purpose: decide whether to proceed to v2 confirmatory. The pilot is exploratory only.
- Problems: the 3 frozen focus problems.
- Arms: random-capture (the v2 random arm: random strategy + --tape-capture, v2 build), tape-noshare, tape-rwlock. 8 workers. n = 200 runs per arm per problem. Seeds 5000 + r, r = 0..199 (5000-5199).
- Pilot-size note: at n = 50 the false-PROCEED rate of criterion (b) under a no-effect null is about 45% (tools/fp_sim.py, 200,000 replicates: 0.447 exponential, 0.446 geometric); at n = 200 it is about 4% (0.038 exponential, 0.037 geometric). Decided before any pilot data. Seeds 5000-5199 are disjoint from Step 4's 20000-20999, from v1 (1000-1099) and from every fuzzer --seed used in v2 development (1 = the fuzzer default and the analysis server, 7 = selftest, 100-102 = analysis server, 999-1019 = warm-ups, benchmarks, smoke and parity runs).
- Kill criterion: PROCEED only if (a) for draw-level tape mutation, measured in Part 2 (2,000 children per problem): mut_changed_input >= 0.80 AND median mut_similarity >= 0.50, on all 3 focus problems, AND (b) at least one problem has median generated tests-to-bug (tests_before + 1) for tape-noshare or tape-rwlock <= 0.70x random-capture. Otherwise STOP tape work.
- Metric note: tests-to-bug means generated tests-to-bug (tests_before + 1, v1's definition) throughout Steps 2e and 4. Reason: random-capture does not dedup, so executed tests-to-bug excludes the tape arms' dup-skips but counts random's duplicates. Decided before any pilot data (Q3 of the Step 2d review).
- Note: v1's mut_changed_input is ~1 by construction (every child draws a fresh seed); mut_similarity is the comparable steering measure.
- The span ablation is not part of the decision.

Part 2 (runs before Part 3). Mutation effectiveness table: the 3 focus problems plus the first non-focus problem alphabetically in each group (arrays, strings, graphs). 2,000 mutated children per mode: v1 guided, tape --tape-mut byte, tape draw-level. Save the (parent, child) recipe pairs; compute mut_similarity offline in Python (outside the timed loop). Report per problem per mode: mut_changed_input, and mut_similarity median and IQR.

Part 3. Run exactly the pilot plan. Report per problem per arm: median/p25/p75 generated tests-to-bug (primary); executed tests-to-bug median/p25/p75 (secondary); median wall_s, generated vs executed, dup_skip, budget/overflow counts. State PROCEED or STOP using only the committed criterion. Run nothing else.

OUTPUT: plan commit hash + timestamp, Part 2 table, Part 3 table, decision.

---

## Step S: Shrinker (runs regardless of the 2e decision; needs 2a)

Scope: tools/shrink.py (or a new C++ shrinker if speed requires), new core/tape_file_runtime.cpp, tools/build.py (new build/tape/ flavour).

Requirements:
0. File-based tape runtime core/tape_file_runtime.cpp: defines the session pointer (Step 2a); maps the input tape from the file named by env var CF_TAPE_IN (absent = empty tape); writes the output tape and draw log to the files named by CF_TAPE_OUT and CF_TAPE_LOG; reads CF_TAPE_FALLBACK_ZERO=1 and CF_TAPE_BUDGET. build.py builds a third flavour build/tape/ of every generator linked with it. The Python shrinker uses these binaries (not the worker shm API from Step 2b).
   Starting from a v1 gallery bug: run the build/tape/ generator with an empty input tape and the v1 seed to capture its tape (this reproduces the v1 input exactly, per Step 2a T2); verify the input hash matches the gallery input before shrinking.
1. Phase 1, tape shrinking with fallback_zero, keeping a candidate only if it still produces the same failure kind:
   - truncate the tape (binary search on length);
   - delete spans of words (lengths 8, 4, 2, 1);
   - set draws to 0;
   - reduce draw values (binary search toward 0).
   Budget-exceeded candidates are rejected, not errors.
2. Phase 2, text-level ddmin on the Phase 1 output: line-level first, then token-level within lines. Every candidate must pass the problem's verifier (invalid candidates are rejected); failure is judged exactly as the fuzzer judges it (ref + fast + checker, same failure kind). Cap 60 s per bug (both phases together).
3. Final output must pass the verifier and still fail the same way. Prefer fewer bytes.
4. Keep the old shrinker available behind a flag for comparison.

Tests:
- T1. Golden check + selftest pass.
- T2. For all 30 gallery bugs: original bytes, old shrinker bytes, new shrinker bytes, verifier_ok, same failure kind. Highlight majority_voting and range_linear_add_range_min.

OUTPUT: diff summary, T2 table, commit hash.

---

## Step 3: trace-cmp value profile (only if 2e = PROCEED)

Scope: tools/build.py (coverage flags), core/fs_runtime.cpp (hooks), core/fuzzer.cpp (admission), docs and CLAUDE.md coverage rule.

Requirements:
1. Also build fast_sol/fast_bug with -fsanitize-coverage=trace-cmp. Implement the __sanitizer_cov_trace_cmp{1,2,4,8} and const_cmp{1,2,4,8} hooks.
2. Feature = (16-bit hash of PC, bucket of floor(log2(|a - b| + 1))), stored in a separate value-profile map. The v1 edge map semantics are unchanged.
3. Flag --value-profile: admission when new edge-bucket OR new value-profile feature. Without the flag, behaviour is unchanged.
4. New exploratory arm: tape-rwlock-vp.
5. Update the CLAUDE.md coverage rule (team-approved).

Tests:
- T1. Golden check + selftest pass; without --value-profile, hunt results are statistically indistinguishable from 2d (20 runs, same seeds, identical tests_before per run expected if RNG use is unchanged; report any difference).
- T2. Show that range_linear_add_range_min's chmin against 1e9 is an instrumented compare site: log its operands for a crafted input with values near 1e9.
- T3. Overhead: tests_per_sec with vs without trace-cmp on the 3 focus problems.

OUTPUT: diff summary, test results, commit hash.

---

## Step 4: v2 confirmatory (only if 2e = PROCEED)

Part 1. Write docs/v2_prereg.md, show it to the user, commit after confirmation, before any run:
- Problems: the 3 frozen focus problems.
- Confirmatory family: random-capture vs tape-noshare, random-capture vs tape-rwlock, tape-noshare vs tape-rwlock (random-capture = the v2 random arm: random strategy + --tape-capture).
- Exploratory family (reported separately): tape-rwlock-span, tape-rwlock-vp (if Step 3 done).
- n = 1000 per arm per problem, 8 workers, seeds 20000 + r. Time budget 20 s; censored runs = +inf.
- Primary metric: generated tests-to-bug (tests_before + 1, v1's definition). Secondary: executed tests-to-bug, wall time.
- Statistics: two-sided Mann-Whitney U, Holm within each family, ratio of medians with 95% bootstrap CI (2000 resamples), Vargha-Delaney A12.
- Scope: these statistics run on generated tests-to-bug (tools/aggregate.py must compute them on that column for the v2 arms); executed tests-to-bug is descriptive only.
- Include the power simulation at n = 1000 (existing aggregate.py method) in the doc before committing.
- All results are reported, including v1 and the pilot, whatever the outcome.

Part 2. Run exactly the plan. Report the tables and statistics. Run nothing else.

OUTPUT: prereg commit hash + timestamp, results tables, statistics.

---

## Tape design spec (content for docs/tape_design.md, Step 2.0)

### Goal
Make pool entries steerable. A v2 recipe = (variant, size, seed, tape). The same recipe always produces byte-identical generator output.

### Words and draws
- A tape is a sequence of uint64 words. With a session active, Random's raw next() returns the next input-tape word while any remain, otherwise the instance's own xoshiro (seeded from the constructor seed exactly as in v1), or 0 if fallback_zero is set.
- Every word returned by raw next() is appended to the OUTPUT tape. An empty input tape therefore reproduces v1 exactly, and the output tape is exactly the consumed words.
- A draw = one call to next(upper); it may consume several words (mask + reject). The draw log records, per draw, (index of the ACCEPTED word in the output tape, upper).
- Draw value = accepted_word & mask(upper), always. Draw-level mutation replaces the WHOLE accepted word with v in [0, upper] (high bits zero). Since v fits under the mask it is accepted first try; earlier rejected words still reject; later words do not shift unless the new value changes how many draws follow (e.g. n).

### Session control (random.h)
- Session pointer to a session struct: defined (strong symbol) in core/fs_runtime.cpp and core/tape_file_runtime.cpp; declared weak extern in random.h, which checks the symbol's address before dereferencing. Absent symbol (build/plain/) or null = exact v1 behaviour (golden test must pass). global_gen unchanged.
- Budget: if total words consumed exceed the session budget, set a flag and _exit with a dedicated code; the fuzzer counts gen_budget_exceeded and treats it as gen_skip.
- Output tape or draw log over shm capacity: set an overflow flag; the test still runs, the child is not admissible (count tape_overflow).

### Shared memory (per worker, generator server only)
header {magic, version, in_len, out_len, log_len, flags, budget, fallback_zero} | input words[CAP] | output words[CAP] | draw log[LOGCAP]. CAP and LOGCAP from feasibility check F5 with 2x headroom.

### Arena
- Process-wide, append-only, bump-allocated (atomic fetch_add) region with tape words + draw logs of admitted entries. Fully written before the handle is published under the pool lock; never modified afterwards; read without locks.
- Locked pool work stays an O(1) handle copy. Arena full: no admission, count arena_full.
- Scale experiments never allocate in the arena; their pool cost is unchanged from v1.

### Mutation (--recipes tape)
- Parent selection identical to v1 (same pool-use probability).
- Child = copy of the parent tape; apply m ops, m = 1 + Geometric(p = 0.5), capped at 8. Each op:
  - 50% value: random draw d, new v uniform in [0, upper_d], different from old if upper_d > 0
  - 25% nudge: v = old +/- k, k uniform in 1..16, clamped to [0, upper_d]
  - 15% copy: random draws d1, d2; if val(d1) <= upper_d2, set val(d2) = val(d1); otherwise retry choosing d2 up to 4 times, then fall back to a value op (the op actually applied is recorded)
  - 10% size: the v1 size-factor op
- --tape-span ablation: the 50% value op becomes 40% value + 10% span: L = 1 + Geometric(mean 8) consecutive draws all set to 0, or all set to their own upper (50/50).
- The child gets a fresh seed (used only past the end of the tape).
- Dedup: hash generator output; if it equals the parent's stored input hash or is in a per-worker set of the last 1024 hashes, skip ref/fast and count dup_skip. Tests with no parent compare only against the per-worker set.
- Diagnostic only (never confirmatory): --tape-mut byte replaces one random byte of one random tape word.

### Metrics added
generated, executed, dup_skip, mut_changed_input (fraction of mutated children whose input hash differs from the parent's), arena_bytes, arena_full, gen_budget_exceeded, tape_overflow.
mut_similarity (offline, Step 2e Part 2 only, never in the timed loop): for a mutated child, difflib.SequenceMatcher ratio between parent and child generator outputs as whitespace token lists, first 20,000 tokens each, computed in Python from saved (parent, child) recipe pairs.

### Arms
random strategy (--strategy random, unchanged v1), tape-noshare, tape-rwlock; ablations tape-rwlock-span and (Step 3) tape-rwlock-vp.
---

## Changelog (2026-10-30)

- D1 Paths: C++ tests live in core/tests/ (built into build/tests/); golden file is core/tests/golden_gen.json; Step 2a scope and test path (core/tests/tape_test.cpp) updated.
- D2 Working rules: dependency rule is now "No dependencies beyond those already in requirements.txt (C++ standard library for C++)."
- D3 Background: next(upper) "masks to the next power of two, and rejects values > upper unless upper+1 is a power of two".
- D4 Terminology: added a note under the Status table defining "random strategy" vs "--recipes random"; Background, Step 2d arms, Step 2e arms and criterion, Step 4 confirmatory family, and the spec's Arms list now say "random strategy".
- D5 Step 0.1: sizes {1, 5, 50, 200} for every generator binary; removed the seed-only and "valid range" clauses.
- D6 Step 0.2: count obtained by replay through build/plain/ generator, ref, fast and checker; new outcome mapping ref_fail (exit 3) / checker_error (crash or non-testlib exit) / WA (WA, PE); neither new outcome triggers first_bug; STOP before changing core/fuzzer.cpp; Status title updated.
- D7 Step 2a + spec Session control: session pointer defined (strong) in core/fs_runtime.cpp (later also core/tape_file_runtime.cpp), weak extern with address check in random.h, build/plain/ = v1, global_gen unchanged; Step 2a scope includes the fs_runtime.cpp definition.
- D8 Step 2b T4: replaced with scale config, --recipes random, 10,000 tests, rwlock, 8 workers, 10 repeats, before (git worktree) vs after.
- D9 Steps 2b T4 and 2c T2: spread = min-max of "before" repeats; STOP if after-median differs by > 5% AND lies outside that range.
- D10 Step 2d requirements + spec: (a) draw write replaces the whole accepted word with v, value read as word & mask(upper); (b) copy op retries d2 up to 4 times then falls back to a value op, applied op recorded (T3 counts applied ops); (c) no-parent tests dedup only against the per-worker recent-hash set.
- D11 Spec metrics + Step 2e Part 2: new offline metric mut_similarity (difflib ratio on whitespace tokens, first 20,000 each, from saved parent/child recipe pairs); Part 2 reports its median and IQR per problem per mode.
- D12 Step 2e: kill criterion (a) = draw-level mutation in Part 2: mut_changed_input >= 0.80 AND median mut_similarity >= 0.50 on all 3 focus problems; Part 2 runs before Part 3; note that v1 mut_changed_input is ~1 by construction.
- D13 Step S: new core/tape_file_runtime.cpp (CF_TAPE_IN/OUT/LOG, CF_TAPE_FALLBACK_ZERO, CF_TAPE_BUDGET), build/tape/ generator flavour used by the Python shrinker; gallery bugs start by capturing the tape with an empty input and the v1 seed, input hash verified first.
- D14 Step S Phase 2: line-level then token-level ddmin; verifier on every candidate; failure judged as the fuzzer judges it (ref + fast + checker, same kind); 60 s cap per bug.
- D15 Status: note that there is no Step 1; the original groundwork prompt became Step 0.
- Step S heading: dependency is "needs 2a" (was "needs 2a-2b"); since D13 the shrinker uses the file-based runtime, not the 2b shm API.
