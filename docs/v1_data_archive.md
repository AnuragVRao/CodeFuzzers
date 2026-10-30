# v1 data archive

Snapshot of `results/` (gitignored) taken before any v2 run. Stored outside the repo; not uploaded.

- Archive: `~/codefuzzers_archive/results_v1_a7252c0.tar.gz` (tar + gzip; zstd was not installed)
- Size: 5,830,815 bytes (5.6 MiB)
- sha256: `be115808e063f2c0008a92e099a2324150ccc91b18fe1e83e1c5e60cd1871288`
- Commit at archive time: `a7252c0` (working tree clean)
- Files: 16,036 (same as `find results -type f` at archive time)
- Top-level directories: bugs, charts, derived, jobs, llm, raw (plus top-level files digest.md, hunt_full.log, pool_bench.csv, rerun.log, runs.csv, scale_full.log, shrink_scaling.csv, summary.json)

Check a copy: `sha256sum results_v1_a7252c0.tar.gz`. Restore: `tar -xzf results_v1_a7252c0.tar.gz` from the repo root.
Note: `results/derived/` was created in Step 0 by tools/replay_first_bugs.py; everything else is v1 output.
