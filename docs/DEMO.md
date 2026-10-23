# Demo script (5 minutes)

## Checklist (before the audience arrives)
- [ ] Laptop **plugged in**, Windows power mode **Best performance**, sleep / screen-off disabled
- [ ] **Ollama running** with `qwen3:8b` pulled (`curl localhost:11434/api/tags`)
- [ ] Analysis server: `python3 tools/server.py`
- [ ] Dashboard: `cd dashboard && source ~/.nvm/nvm.sh && npm run dev`, open http://localhost:5173 (1280×720)
- [ ] `python3 tools/build.py` is up to date; `tools/selftest.sh` passes
- [ ] A clean history: move `results/jobs/` away (`mv results/jobs results/jobs.bak`) before starting the server
- [ ] Nothing else heavy running (browser tabs, builds)

## Order

1. **Overview** (30 s) — the headline results.
   - One sentence: parallel differential fuzzer for competitive-programming solutions; shared coverage-guided pool.
   - Point at: the headline numbers (speed-up at 20 workers, bugs found).
2. **Scaling** (60 s) — pick a problem, workload K=0.
   - Shared pools vs `noshare` at K=0: the speed-up is close to the no-sharing baseline — sharing is nearly free when
     tests are the cost. Point at the speed-up line at 20 workers.
   - Switch to the high-contention workload: the **snapshot** strategy collapses (copy cost). Point at its throughput.
3. **Hunt** (45 s) — time-to-bug.
   - Guided search finds hard bugs in a bounded number of tests; the null result (no significant difference between
     strategies on some problems) is reported, not hidden. Point at the median tests-to-bug and the CI.
4. **Analyze** (2 min)
   1. Click **affine_point_bug** (≈ 20 s). While it runs, point at the stage timeline. Then: verdict "Bug found: WA after N
      tests"; failing test shrunk to 2 numbers (**899 → 43 bytes**); the **LLM card** is labelled *unverified suggestion*
      with its measured accuracy (7/29 within ±3 lines, chance ≈ 7 %).
   2. Start **range_min_correct** at 1 min. Clean report: "No failing input found in N tests… fewer than X %" — a
      **bound, not a proof**; point at N and the log-uniform size remark. Mention the calibration chart (size cap) and the
      performance section (speed-up, noshare vs rwlock ratio ≈ 1).
   3. Click **broken_compile**: fails in under a second with the compiler output — fast, clear failure.
5. **Bugs** (30 s) — the gallery of 30 planted bugs: open one card; the diff highlights the first differing token; the
   LLM column shows ✓/✗ against the planted line.

## If something goes wrong
- Analyze tab says "server not running": start `python3 tools/server.py`.
- A job is slow or stuck: Cancel in the job view; the history keeps it.
- No LLM card: Ollama is not running or `qwen3:8b` is missing; the analysis itself is unaffected.
