"""Step 2e Part 3 report (read-only on results/raw/pilot). Criterion (b) exactly as in docs/v2_pilot_plan.md:
median generated tests-to-bug (tests_before + 1, censored = +inf) per arm x problem over the 200 runs; an arm with
more than half censored has an undefined median and cannot satisfy (b); PASS if tape / random-capture <= 0.70.
Quantiles use tools/aggregate.py quant() (numpy linear interpolation, the project's existing method).
Infrastructure failures (Amendment 1): missing run JSON (run.py FAILED), or a run without a bug whose wall_s < 20."""
import json, math, sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/anura/PC Project/CodeFuzzers")
sys.path.insert(0, str(ROOT / "tools"))
from aggregate import quant  # noqa: E402

RAW = ROOT / "results" / "raw" / "pilot"
PROBLEMS = ["majority_voting", "range_linear_add_range_min", "longest_common_substring"]
ARMS = ["random-capture", "tape-noshare", "tape-rwlock"]
STRATEGY = {"random-capture": "random", "tape-noshare": "noshare", "tape-rwlock": "rwlock"}
INF = math.inf
f = lambda x: "undefined" if x is None else ("+inf" if x == INF else f"{x:,.1f}")

runs, failures, commits, dirty, blocks = {}, [], Counter(), Counter(), Counter()
for p in PROBLEMS:
    for a in ARMS:
        rs = []
        for r in range(200):
            path = RAW / p / f"{a}_w8_k0_f0_r{r}.json"
            if not path.exists():
                failures.append((p, a, r, "missing run JSON (run.py reported FAILED)"))
                continue
            d = json.loads(path.read_text())
            c = d["config"]
            assert c["strategy"] == STRATEGY[a] and c["seed"] == 5000 + r and c["workers"] == 8 and c["fast"] == "bug"
            assert (c["recipes"] == "tape") == a.startswith("tape-") and bool(c["tape_capture"]) == (a == "random-capture")
            commits[d.get("git_commit")] += 1
            dirty[d.get("git_dirty")] += 1
            blocks[d.get("block_seed") == 5000 + r] += 1
            fb = d["first_bug"]
            if fb is None and d["wall_s"] < 20:
                failures.append((p, a, r, f"no bug and wall_s {d['wall_s']} < 20"))
            rs.append(dict(r=r, d=d, gen=fb["tests_before"] + 1 if fb else INF, exe=fb["executed_before"] + 1 if fb else INF))
        runs[(p, a)] = rs


def median_or_undefined(vals):
    censored = sum(v == INF for v in vals)
    return (None if censored > len(vals) / 2 else quant(vals, 50)), censored


print(f"run JSONs: {sum(len(v) for v in runs.values())} / 1800; git_commit {dict(commits)}; git_dirty {dict(dirty)}; "
      f"block_seed == 5000 + r: {dict(blocks)}")
print(f"infrastructure failures (Amendment 1): {len(failures)}")
for x in failures:
    print("  ", x)

print("\n=== (a) CRITERION (b): median generated tests-to-bug (tests_before + 1), censored = +inf")
print("| problem | arm | n | censored | median | ratio vs random-capture | <= 0.70 |")
print("|---|---|---:|---:|---:|---:|---|")
any_pass = False
for p in PROBLEMS:
    base, _ = median_or_undefined([x["gen"] for x in runs[(p, "random-capture")]])
    for a in ARMS:
        vals = [x["gen"] for x in runs[(p, a)]]
        med, cens = median_or_undefined(vals)
        if a == "random-capture":
            print(f"| {p} | {a} | {len(vals)} | {cens} | {f(med)} | - | - |")
            continue
        if med is None or base is None or not math.isfinite(base):
            ratio, verdict = None, "FAIL (median undefined)"
        else:
            ratio = med / base
            verdict = "PASS" if ratio <= 0.70 else "FAIL"
            any_pass |= ratio <= 0.70
        print(f"| {p} | {a} | {len(vals)} | {cens} | {f(med)} | {'undefined' if ratio is None else f'{ratio:.3f}'} | {verdict} |")
print(f"\noverall (b): {'PASS' if any_pass else 'FAIL'}" + ("  (WITHHELD: infrastructure failures, Amendment 1)" if failures else ""))

print("\n=== (b) DESCRIPTIVE (not part of the criterion)")
print("| problem | arm | gen p25 | gen p75 | executed median | executed p25 | executed p75 | median wall_s | dup_skip (sum) | gen_budget_exceeded (sum) | tape_overflow (sum) | runs with arena_full > 0 |")
print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
arena_runs = []
for p in PROBLEMS:
    for a in ARMS:
        rs = runs[(p, a)]
        g, e = [x["gen"] for x in rs], [x["exe"] for x in rs]
        q = lambda v, k: quant(v, k)
        af = [x for x in rs if x["d"]["arena_full"] > 0]
        arena_runs += [f"results/raw/pilot/{p}/{a}_w8_k0_f0_r{x['r']}.json (arena_full {x['d']['arena_full']})" for x in af]
        print(f"| {p} | {a} | {f(q(g, 25))} | {f(q(g, 75))} | {f(q(e, 50))} | {f(q(e, 25))} | {f(q(e, 75))} | "
              f"{quant([x['d']['wall_s'] for x in rs], 50):.3f} | {sum(x['d']['dup_skip'] for x in rs)} | "
              f"{sum(x['d']['gen_budget_exceeded'] for x in rs)} | {sum(x['d']['tape_overflow'] for x in rs)} | {len(af)} |")
print("runs with arena_full > 0:", arena_runs or "none")
