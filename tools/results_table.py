#!/usr/bin/env python3
"""Prints the README's key-results table (markdown) from results/summary.json, plus the commits
the summarised runs came from, so the README numbers can always be regenerated and checked.
Usage: python3 tools/results_table.py
"""
import json
from statistics import median
import problems

s = json.loads((problems.ROOT / "results" / "summary.json").read_text())
sc, rows = s["scale"], []


def add(metric, value):
    rows.append((metric, value))


for p in sorted({r["problem"] for r in sc}):
    r = next(r for r in sc if (r["problem"], r["strategy"], r["K"], r["workers"]) == (p, "noshare", 0, 20))
    add(f"Speed-up of noshare at 20 workers, {p} (weak scaling, vs 1 worker)", f"{r['speedup_abs']:.2f}×")
k0 = [r["vs_noshare"] for r in sc if r["K"] == 0 and r["strategy"] != "noshare" and r["workers"] > 1]
add("Sharing strategies vs noshare at K=0 (all problems, 2–20 workers)", f"{min(k0):.3f} – {max(k0):.3f}")
for strategy in ("rwlock", "snapshot"):
    for k, f in ((50, 0.1), (50, 0.5)):
        v = [r["vs_noshare"] for r in sc if (r["strategy"], r["K"], r["F"], r["workers"]) == (strategy, k, f, 20)]
        add(f"{strategy} vs noshare at 20 workers, K={k}/F={f} (range over problems)", f"{min(v):.2f} – {max(v):.2f}")
snap = [r for r in sc if (r["strategy"], r["K"], r["F"], r["workers"]) == ("snapshot", 50, 0.5, 20)]
add("snapshot at K=50/F=0.5, 20 workers: measured vs predicted tests/s (pool_bench ceiling)",
    ", ".join(f"{r['problem']} {r['tps_median']:.0f} vs {r['predicted_tps']:.0f}" for r in snap))
pin = s["pinning"]
add("CPU pinning gain (global, 8 workers, median of 5)",
    f"+{100 * (pin['ratio'] - 1):.0f}% ({pin['pinned']['median']:.0f} vs {pin['unpinned']['median']:.0f} tests/s)")
for t in (t for t in s["hunt_tests"] if t["family"] == "confirmatory"):
    add(f"Confirmatory hunt, {t['problem']}: {t['b']} / {t['a']} median tests-to-bug (8 workers, n=100)",
        f"{t['ratio']:.2f} [95% CI {t['ratio_ci_lo']:.2f}–{t['ratio_ci_hi']:.2f}], p_Holm = {t['p_holm']:.2f}")
ex = [t for t in s["hunt_tests"] if t["family"] == "exploratory"]
add("Exploratory hunt comparisons with p_Holm < 0.05", f"{sum(t['p_holm'] < 0.05 for t in ex)} of {len(ex)}")
mde = s["power"]["mde_ratio"]
add("Minimum detectable median ratio (Mann–Whitney, 80% power)", f"n=30: {mde['30']}×, n=100: {mde['100']}×")
g = s["shrink"]["gallery"]
add("Shrinker: median bytes kept / bugs re-validated",
    f"{100 * median(r['bytes_shrunk'] / r['bytes_original'] for r in g):.0f}% / {sum(r['mismatch_ok'] for r in g)} of {len(g)}")
add("Shrinker speed-up at 20 worker processes (median over 3 problems)", f"{s['meta']['headline']['shrink_speedup_20']:.1f}×")
for model, d in s["llm"].items():
    e = d["explain"]
    add(f"LLM {model}: bug line within ±3 (chance) / category (majority baseline)",
        f"{e['line_hits']}/{e['n_explained']} ({100 * e['chance_line_acc']:.0f}%, p = {e['line_p']:.3f}) / "
        f"{e['category_hits']}/{e['n_explained']} ({e['majority_category']} {100 * e['majority_share']:.0f}%, p = {e['category_p']:.2f})")
    if "gen" in d:
        gn = d["gen"]
        add(f"LLM {model}: generators compiled (first try + after repair) / mean verifier acceptance",
            f"{gn['compiled_first_try']} + {gn['compiled_after_repair']} of {gn['n']} / {100 * gn['mean_acceptance']:.0f}%")

print("| Result | Value |\n|---|---|")
for m, v in rows:
    print(f"| {m} | {v} |")
print(f"\nGenerated from results/summary.json ({s['meta']['generated_at']}); runs from commits {', '.join(s['meta']['commits'])}.")
