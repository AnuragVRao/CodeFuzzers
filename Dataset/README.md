# CodeFuzzers benchmark suite

30 competitive-programming problems for differential testing (fast solution vs. brute force),
all derived from [Library Checker](https://github.com/yosupo06/library-checker-problems)
(commit `1814c4e5205517e368bb57a8d1127eb961cfeaae`, Apache-2.0).

| Group | Problems | Notes |
|---|---|---|
| `problems/arrays/`  | 12 | data-structure problems (range queries, convex-hull trick, ...) |
| `problems/strings/` |  8 | Z-function, suffix array, palindromes, LCS, ... |
| `problems/graphs/`  | 10 | 5 general-graph problems and 5 tree problems (`subtype: tree` in meta.json) |

25 problems compare output exactly; 5 use a custom checker (`checker_kind: custom` in meta.json).

## Layout of one problem

    problems/<group>/<name>/
      sol.cpp        fast solution (Library Checker's correct.cpp, unmodified)
      brute.cpp      slow reference (Library Checker's naive.cpp, or authored here: see meta.json "brute_origin")
      verifier.cpp   input validator (testlib)
      checker.cpp    output checker (testlib): exact-match, or custom for problems with several valid answers
      params.h       constants generated from Library Checker's info.toml
      gen/generator.cpp   seeded generator: ./generator <seed> [size]
      meta.json      provenance, generator kind, checker kind, known issues, planted_bugs (empty for now)

`generator.kind` is `native-small` (Library Checker's own small generator, ignores the size argument)
or `authored-size-knob` (written here; second argument caps the input size). Some problems also have
`gen/generator_alt_N.cpp`. Everything is deterministic: the same seed gives the same input.

## Build and test

    g++ -O2 -std=c++17 -I common -I problems/arrays/range_add_range_min -o sol problems/arrays/range_add_range_min/sol.cpp
    python3 tools/validate.py --seeds 300            # all problems; see VALIDATION_SUMMARY.md
    python3 tools/validate.py --only zalgorithm      # one problem

Generator, verifier and checker are compiled with `-I common -I <problem dir>` (generators include `../params.h`).

## Known issues

* `enumerate_triangles`: the upstream generator aborts on a few seeds (e.g. 232); skip seeds where the generator exits non-zero.
* No planted bugs yet (Library Checker ships no wrong-answer solutions).
* Authored generators default to very small inputs (size knob 4-32 in the validator); raise it for fuzzing.
