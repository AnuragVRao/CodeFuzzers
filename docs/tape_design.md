# Tape design (v2)

Specification for v2 (tape) recipes, copied from the "Tape design spec" section of docs/v2_roadmap.md
(Step 2.0) with CAP/LOGCAP filled in. The v1 recipe rule in CLAUDE.md stays in force for all v1
experiments and all scale experiments.

### Goal
Make pool entries steerable. A v2 recipe = (variant, size, seed, tape). The same recipe always produces byte-identical generator output.

### Words and draws
- A tape is a sequence of uint64 words. With a session active, Random's raw next() returns the next input-tape word while any remain, otherwise the instance's own xoshiro (seeded from the constructor seed exactly as in v1), or 0 if fallback_zero is set.
- The instance's own xoshiro stream does not advance while input-tape words are consumed; past the end of the tape it starts from the seed's first word. Replay never reaches the fallback because a stored tape is the full consumed sequence; a mutated child has a fresh seed, so its fallback words are new.
- Every word returned by raw next() is appended to the OUTPUT tape. An empty input tape therefore reproduces v1 exactly, and the output tape is exactly the consumed words.
- A draw = one call to next(upper); it may consume several words (mask + reject). The draw log records, per draw, (index of the ACCEPTED word in the output tape, upper).
- Draw value = accepted_word & mask(upper), always. Draw-level mutation replaces the WHOLE accepted word with v in [0, upper] (high bits zero). Since v fits under the mask it is accepted first try; earlier rejected words still reject; later words do not shift unless the new value changes how many draws follow (e.g. n).

### Session control (random.h)
- Session pointer to a session struct: defined (strong symbol) in core/fs_runtime.cpp and core/tape_file_runtime.cpp; declared weak extern in random.h, which checks the symbol's address before dereferencing. Absent symbol (build/plain/) or null = exact v1 behaviour (golden test must pass). global_gen unchanged.
- Budget: if total words consumed exceed the session budget, set a flag and _exit with a dedicated code; the fuzzer counts gen_budget_exceeded and treats it as gen_skip.
- Budget value: 1,000,000 words, fixed; the default for every armed run from Step 2d on (about 10x CAP, so long tapes overflow long before they hit the budget). Exit code 85; reported by the server client as status BUDGET.
- Output tape or draw log over shm capacity: set an overflow flag; the test still runs, the child is not admissible (count tape_overflow).

### Shared memory (per worker, generator server only)
header {magic, cap, log_cap, in_off, out_off, log_off, out_len, log_len, consumed, flags} (80 bytes, padded to 128) | input words[CAP] | output words[CAP] | draw log[LOGCAP] (16-byte entries {accepted-word index, upper}).
- magic carries the version in its low bits ("CFTAPE" v1). cap, log_cap and the byte offsets are set once by the worker. in_len, budget and fallback_zero travel in the per-test Request (with the arm flag), not in the header.
- flags: OVERFLOW = 1, BUDGET = 2, COMPLETE = 4. Before forking an armed request the SERVER clears out_len, log_len, consumed and flags. On a normal exit (exit() or return from main, any exit code) the child writes out_len and log_len (capped at CAP / LOGCAP), consumed (all words, may exceed CAP), and LAST flags with COMPLETE. A budget exit (_Exit 85), a crash or a timeout writes no header field, so COMPLETE stays 0.
- The output-tape and draw-log spans are valid only when COMPLETE is set (and only until the next request on that server). Step 2d must never admit a child without COMPLETE (and never one with OVERFLOW).
- Admission rule (Step 2d on): a tape child may enter the pool only if its generator status is OK AND COMPLETE is set AND
  OVERFLOW is not set (BUDGET implies status not OK), and it reached new coverage. Generators that exit non-zero (skip a
  seed) still set COMPLETE, so the status check is required.
- Layout rule: the shm header contains ONLY offsets, lengths, flags and counters, never pointers. The child builds its local session struct (pointers) from the mapping after fork, before main().
- CAP = 97,930 words, LOGCAP = 79,446 draw-log entries: 2x the largest raw-word and draw counts over ALL 37
  generator binaries, measured with an instrumented copy of random.h (scratchpad only):
  - all 37: seeds 1..2000 at size 200, seeds 7919k (k = 1..20) at every size 1..200, golden seeds at 200
    (222,185 runs); connected_components_of_complement_graph also seeds 1..5000 at size 200 (Step 2.0 F5).
  - Maxima: connected_components_of_complement_graph 48,965 words / 39,723 draws (seed 3597, size 200);
    next largest two/three_edge_connected_components gen_alt 6,854 / 5,549; all others <= 2,376 / 1,603.
  - Analytic draw maximum of connected_components_of_complement_graph at size 200: 19,899 shuffle draws
    + 19,900 uniform_bool draws + 3 = 39,802, within LOGCAP. Raw words have no hard bound (rejection), so a
    longer tape sets the overflow flag (tape_overflow), never a crash.
  - enumerate_triangles aborts (assert in uniform(), lower > upper) on some seeds at size 200 after <= 3 words;
    the fuzzer treats that as gen_skip.
- Per-worker generator shm with 16-byte draw-log entries (accepted-word index + upper):
  64 + 16 x CAP + 16 x LOGCAP = 2,838,080 bytes (2.84 MB, 2.71 MiB).

### Arena
- Process-wide, append-only, bump-allocated (atomic fetch_add) region with tape words + draw logs of admitted entries. Fully written before the handle is published under the pool lock; never modified afterwards; read without locks.
- Locked pool work stays an O(1) handle copy. Arena full: no admission, count arena_full.
- Scale experiments never allocate in the arena; their pool cost is unchanged from v1.
- As built (core/arena.hpp, Step 2c): Arena reserves the region with mmap(MAP_NORESERVE), default 1 GiB (fuzzer --arena-mb).
  store() = fetch_add + copy; the first allocation that does not fit closes the arena (later stores also fail, arena_full).
  The caller checks pool->novel(cov) first, so only tapes that would be admitted are copied; a tape whose report() then
  loses the race to another writer stays in the arena unused. arena_bytes in the run JSON = bytes used (= peak).
- Handle: TapeHandle {offset, words, draws, input_hash} (24 bytes). Pool entry: TapeEntry = Entry's fields + TapeHandle
  (48 bytes).
- Entry-type choice: the pool (core/pool.hpp) is a template on its entry type. Pool, GlobalLock, ..., make_pool() are the
  v1 instantiation with Entry (24 bytes, static_assert), so v1 and scale runs keep their entry size and Snapshot copy
  cost; tape runs use make_pool<TapeEntry>(). The only addition to the v1 pools is a read-only virtual novel(cov),
  which v1 code never calls.

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
