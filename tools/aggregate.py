#!/usr/bin/env python3
"""Aggregates all results into results/summary.json. Run tools/flatten.py first.
Inputs: results/runs.csv, results/pool_bench.csv, results/shrink_scaling.csv, results/bugs/gallery.json,
Dataset/bugs.json. Scale and pinning use only the new randomised "scale"/"pinning" experiments (v1 runs
appear only in order_effect); hunt falls back to hunt-quick if the full hunt has no rows.
Formulas (tps = tests_per_sec; medians and quartiles over the repeats of one configuration):
  speedup_abs    = tps_median / tps_median(noshare, same problem/K/F, workers=1)
  speedup_rel    = tps_median / tps_median(same strategy/problem/K/F, workers=1)
  efficiency_abs = speedup_abs / workers
  vs_noshare     = tps_median / tps_median(noshare, same problem/K/F/workers)
  predicted_tps  = min(noshare tps_median at this W, pool_bench tests_per_sec at this strategy/K/F/threads)
  hunt censoring = a run without a bug counts as +inf tests/time; a quantile touching +inf -> null + flag
  hunt_tests     = two-sided Mann-Whitney U on tests-to-bug (censored = +inf); p_holm = Holm within a family:
                   "exploratory" (hunt) and "confirmatory" (hunt-focus)
  ratio          = median_b / median_a (null if either median is censored)
  ratio CI       = 95% percentile bootstrap of median_b / median_a (2000 resamples of each group, fixed seed)
  power          = smallest ratio r (1.1..4.0 step 0.1) that a two-sided Mann-Whitney U at alpha 0.05 detects
                   with >= 80% power, simulated with geometric tests-to-bug (baseline median = range_add_range_min
                   noshare @ 8 workers, other group median x r), 500 simulations per r
  order_effect   = vs_noshare per strategy for range_add_range_min, K=0, 20 workers: v1 (blocked order) vs new
  llm            = per model (results/llm/*.json): explain line/category accuracy vs chance (mean 7/lines), median
                   latency; gen compile counts, mean verifier acceptance, bug rate vs the dataset generator
  hunt_time_scaling = geometric mean over problems of time_median (censored medians skipped and counted)
  pinning ratio  = median(pinned tps) / median(unpinned tps);  shrink speedup = median wall(W=1) / median wall(W)
  mean_size      = median over repeats of the run's average generator size (null for older runs without it)
  headline       = speedup_20_<s>_k0 = median over scale problems of speedup_abs (s, K=0, F=0, 20 workers)
                   for s = rwlock and noshare; pinning ratio, bugs found/total, median(shrunk/original bytes),
                   median over problems of shrink speedup at 20 workers
Usage: python3 tools/aggregate.py [--selftest | --power]
"""
import csv, json, math, sys, warnings
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np
from scipy.stats import mannwhitneyu
import problems
from style import STRATEGY_COLORS

R = problems.ROOT / "results"
INF = math.inf


def read_csv(path):
    if not path.exists():
        print(f"warning: {path.relative_to(problems.ROOT)} missing", file=sys.stderr)
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def num(x):
    """Finite float -> rounded float; inf/nan -> None (JSON-safe)."""
    return None if x is None or not math.isfinite(x) else round(float(x), 6)


def quant(values, q):
    """Linear-interpolated quantile; +inf entries (censored) make the result non-finite."""
    with np.errstate(invalid="ignore"):
        return float(np.percentile(np.array(values, dtype=float), q)) if values else math.nan


def qstats(values, prefix):
    """{prefix_median, prefix_q1, prefix_q3} with null + <stat>_censored when a quantile is censored."""
    out = {}
    for name, q in (("median", 50), ("q1", 25), ("q3", 75)):
        v = quant(values, q)
        out[f"{prefix}_{name}"] = num(v)
        if not math.isfinite(v):
            out[f"{prefix}_{name}_censored"] = True
    return out


def section(rows, exp):
    """Rows of the full experiment, or of exp-quick if the full one is empty -> (rows, preset)."""
    full = [r for r in rows if r["experiment"] == exp]
    return (full, "full") if full else ([r for r in rows if r["experiment"] == f"{exp}-quick"], "quick")


def scale_section(rows, bench):
    g, sizes = defaultdict(list), defaultdict(list)
    for r in rows:
        key = (r["problem"], r["strategy"], int(r["K"]), float(r["F"]), int(r["workers"]))
        g[key].append(float(r["tests_per_sec"]))
        if r.get("mean_size"):  # missing in runs made before mean_size existed
            sizes[key].append(float(r["mean_size"]))
    med = {k: quant(v, 50) for k, v in g.items()}
    pb = {(r["strategy"], int(r["extra_ops"]), float(r["write_frac"]), int(r["threads"])): float(r["tests_per_sec"])
          for r in bench}
    out = []
    for (p, s, k, f, w), v in sorted(g.items()):
        m = med[(p, s, k, f, w)]
        ns1, self1, nsw = (med.get(key, math.nan) for key in ((p, "noshare", k, f, 1), (p, s, k, f, 1), (p, "noshare", k, f, w)))
        sp = m / ns1
        bench_tps = pb.get((s, k, f, w))
        out.append(dict(problem=p, strategy=s, K=k, F=f, workers=w, n=len(v), **qstats(v, "tps"),
                        speedup_abs=num(sp), speedup_rel=num(m / self1), efficiency_abs=num(sp / w),
                        vs_noshare=num(m / nsw), mean_size=num(quant(sizes[(p, s, k, f, w)], 50)) if sizes[(p, s, k, f, w)] else None,
                        predicted_tps=num(min(nsw, bench_tps)) if bench_tps is not None else None))
    return out


def hunt_values(rows):
    """(problem, strategy, workers) -> (tests list, time list) with +inf for censored runs."""
    g = defaultdict(lambda: ([], []))
    for r in rows:
        found = r["bug_found"] == "1"
        t, s = g[(r["problem"], r["strategy"], int(r["workers"]))]
        t.append(float(r["bug_tests_before"]) if found else INF)
        s.append(float(r["bug_time_s"]) if found else INF)
    return g


def hunt_section(g, kinds):
    return [dict(problem=p, strategy=s, workers=w, n=len(t), found=sum(map(math.isfinite, t)),
                 censored=sum(not math.isfinite(x) for x in t), kind=kinds.get(p),
                 **qstats(t, "tests"), **qstats(tm, "time"), values=[num(x) for x in t])
            for (p, s, w), (t, tm) in sorted(g.items())]


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, running = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = running
    return adj


def ratio_ci(ta, tb, seed, n_boot=2000):
    """95% percentile bootstrap CI of median(b) / median(a); +inf (censored) values stay +inf."""
    rng = np.random.default_rng(seed)
    a, b = np.array(ta, dtype=float), np.array(tb, dtype=float)
    ma = np.median(a[rng.integers(0, len(a), (n_boot, len(a)))], axis=1)
    mb = np.median(b[rng.integers(0, len(b), (n_boot, len(b)))], axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = mb / ma  # inf/inf -> nan (undefined), dropped by nanpercentile
    lo, hi = np.nanpercentile(r, [2.5, 97.5]) if np.isfinite(r).any() or np.isinf(r).any() else (math.nan, math.nan)
    return num(lo), num(hi)


def hunt_tests_section(g, family, seed0=0):
    out = []
    for p, w in sorted({(p, w) for p, _, w in g}):
        for comparison, a, b in (("guidance", "random", "noshare"), ("sharing", "noshare", "rwlock")):
            if (p, a, w) not in g or (p, b, w) not in g:
                continue
            ta, tb = g[(p, a, w)][0], g[(p, b, w)][0]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pr = float(mannwhitneyu(ta, tb, alternative="two-sided").pvalue)
            ma, mb = quant(ta, 50), quant(tb, 50)
            lo, hi = ratio_ci(ta, tb, seed0 + len(out))
            out.append(dict(family=family, problem=p, workers=w, comparison=comparison, a=a, b=b, median_a=num(ma),
                            median_b=num(mb), ratio=num(mb / ma) if math.isfinite(ma) and math.isfinite(mb) and ma > 0 else None,
                            ratio_ci_lo=lo, ratio_ci_hi=hi, p_raw=num(pr if math.isfinite(pr) else 1.0)))
    return out


def hunt_time_scaling(hunt_rows, hard):
    g = defaultdict(list)
    for r in hunt_rows:
        if r["problem"] in hard:
            g[(r["strategy"], r["workers"])].append(r["time_median"])
    out = []
    for (s, w), meds in sorted(g.items()):
        ok = [m for m in meds if m is not None and m > 0]
        out.append(dict(strategy=s, workers=w, geomean_time_median=num(math.exp(np.mean(np.log(ok)))) if ok else None,
                        problems=len(ok), skipped_censored=len(meds) - len(ok)))
    return out


def pinning_section(rows):
    out = {}
    for name, pin in (("pinned", "1"), ("unpinned", "0")):
        v = [float(r["tests_per_sec"]) for r in sorted(rows, key=lambda r: int(r["repeat"])) if r["pinned"] == pin]
        out[name] = dict(values=v, median=num(quant(v, 50)), q1=num(quant(v, 25)), q3=num(quant(v, 75)))
    if out["pinned"]["median"] and out["unpinned"]["median"]:
        out["ratio"] = num(out["pinned"]["median"] / out["unpinned"]["median"])
    return out


def snippet(row, path, key, limit=3000):
    """Embed a text file in row[key] (first `limit` chars); row[key_truncated] = True if cut."""
    text = path.read_text(errors="replace") if path.exists() else ""
    row[key] = text[:limit]
    if len(text) > limit:
        row[f"{key}_truncated"] = True


def llm_section(shrink):
    """Per-model summaries from results/llm/; gallery rows get each model's explanation and marks."""
    out = {}
    for f in sorted((R / "llm").glob("explain_*.json")):
        d = json.loads(f.read_text())
        s, model = d["summary"], d["summary"]["model"]
        out.setdefault(model, {})["explain"] = {k: s[k] for k in ("n", "n_explained", "n_too_long", "line_acc",
                                                                  "category_acc", "chance_line_acc", "median_latency_s")}
        by_problem = {r["problem"]: r for r in d["problems"]}
        for row in shrink["gallery"]:
            r = by_problem.get(row["problem"])
            if r:
                row.setdefault("llm", {})[model] = {k: r.get(k) for k in ("status", "line", "category", "explanation",
                                                                          "fix", "line_ok", "category_ok", "latency_s")}
    for f in sorted((R / "llm").glob("gen_*.json")):
        s = json.loads(f.read_text())["summary"]
        out.setdefault(s["model"], {})["gen"] = {k: s[k] for k in ("n", "compiled_first_try", "compiled_after_repair",
                                                                   "mean_acceptance", "mean_llm_bug_rate", "mean_dataset_bug_rate")}
    return out


def shrink_section(gallery, scaling):
    groups = {p["name"]: p["group"] for p in problems.load()}
    rows = []
    for g in gallery:
        if "shrunk" not in g:
            continue
        row = dict(problem=g["problem"], group=groups[g["problem"]], tier=g["tier"], kind=g["kind"],
                   category=g["category"], description=g["description"], trigger=g["trigger"],
                   size_original=g["original"]["size"], size_shrunk=g["shrunk"]["size"],
                   bytes_original=g["original"]["bytes"], bytes_shrunk=g["shrunk"]["bytes"],
                   tests_used=g["tests_used"], wall_s=g["wall_s"], mismatch_ok=g["mismatch_ok"])
        d = R / "bugs" / g["problem"] / "shrunk"
        for key, f in (("input", "input.txt"), ("ref_out", "ref_out.txt"), ("fast_out", "fast_out.txt")):
            snippet(row, d / f, key)
        rows.append(row)
    g = defaultdict(list)
    for r in scaling:
        g[(r["problem"], int(r["workers"]))].append(float(r["wall_s"]))
    sc = []
    for (p, w), v in sorted(g.items()):
        base = quant(g[(p, 1)], 50) if (p, 1) in g else math.nan
        sc.append(dict(problem=p, workers=w, n=len(v), wall_median=num(quant(v, 50)), speedup=num(base / quant(v, 50))))
    return dict(gallery=rows, scaling=sc)


def headline(scale, pinning, shrink, bugs_total):
    def sp20(strategy):
        v = [r["speedup_abs"] for r in scale if (r["strategy"], r["K"], r["F"], r["workers"]) == (strategy, 0, 0.0, 20)
             and r["speedup_abs"] is not None]
        return num(quant(v, 50)) if v else None
    g = shrink["gallery"]
    s20 = [r["speedup"] for r in shrink["scaling"] if r["workers"] == 20 and r["speedup"] is not None]
    return dict(speedup_20_rwlock_k0=sp20("rwlock"), speedup_20_noshare_k0=sp20("noshare"),
                pinning_ratio=pinning.get("ratio"), bugs_found=sum(bool(r["mismatch_ok"]) for r in g),
                bugs_total=bugs_total,
                median_shrink_bytes_ratio=num(quant([r["bytes_shrunk"] / r["bytes_original"] for r in g], 50)) if g else None,
                shrink_speedup_20=num(quant(s20, 50)) if s20 else None)


def power_section(base_median, ns=(30, 100), sims=500, seed=12345):
    """Minimum detectable median ratio for Mann-Whitney U (two-sided, alpha 0.05, 80% power) per n."""
    def p_for(median):  # geometric distribution (support 1, 2, ...) whose median is ~ `median`
        return 1 - 2 ** (-1 / median)
    mde = {}
    for n in ns:
        rng = np.random.default_rng(seed + n)
        mde[str(n)] = None
        for r in np.arange(1.1, 4.0001, 0.1):
            a = rng.geometric(p_for(base_median), (sims, n))
            b = rng.geometric(p_for(base_median * r), (sims, n))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                power = float(np.mean(mannwhitneyu(a, b, alternative="two-sided", axis=1).pvalue < 0.05))
            if power >= 0.8:
                mde[str(n)] = round(float(r), 1)
                break
    return dict(mde_ratio=mde, base_median=base_median, alpha=0.05, target_power=0.8, simulations=sims,
                baseline="range_add_range_min noshare @ 8 workers (hunt)")


def order_effect_section(v1_rows, new_rows):
    """vs_noshare per strategy for range_add_range_min, K=0, 20 workers: v1 (blocked order) vs new (randomised)."""
    pick = lambda rows: {r["strategy"]: r["vs_noshare"] for r in scale_section(rows, [])
                         if (r["problem"], r["K"], r["F"], r["workers"]) == ("range_add_range_min", 0, 0.0, 20)}
    v1, new = pick(v1_rows), pick(new_rows)
    return [dict(strategy=s, vs_noshare_v1=v1.get(s), vs_noshare_new=new.get(s)) for s in sorted(set(v1) | set(new))]


def selftest():
    """Synthetic hunt data: 30 runs with 10 / 20 censored -> median finite / null + flag."""
    ok = True
    for case, censored, want_null in (("A", 10, False), ("B", 20, True)):
        rows = [dict(problem="p", strategy="s", workers="8", bug_found="0" if i < censored else "1",
                     bug_tests_before=str(100 + i), bug_time_s=str(1 + i)) for i in range(30)]
        h = hunt_section(hunt_values(rows), {})[0]
        good = (h["tests_median"] is None and h.get("tests_median_censored") is True) if want_null \
            else (h["tests_median"] is not None and "tests_median_censored" not in h)
        ok &= good
        print(f"case {case}: 30 runs, {censored} censored -> tests_median={h['tests_median']}, "
              f"censored_flag={h.get('tests_median_censored', False)}: {'PASS' if good else 'FAIL'}")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--power" in sys.argv:
        base = next(r["tests_median"] for r in json.loads((R / "summary.json").read_text())["hunt"]
                    if (r["problem"], r["strategy"], r["workers"]) == ("range_add_range_min", "noshare", 8))
        print(json.dumps(power_section(base), indent=1))
        return 0
    runs = read_csv(R / "runs.csv")
    commits = sorted({r.get("git_commit") or "unknown" for r in runs})
    if len(commits) > 1:
        print(f"warning: runs.csv mixes code versions: commits {commits}", file=sys.stderr)
    if "unknown" in commits:
        print("warning: some runs have no git commit recorded (made before run.py stamped it)", file=sys.stderr)
    if any(r.get("git_dirty") == "1" for r in runs):
        print("warning: some runs were made from a dirty working tree", file=sys.stderr)

    bugs = json.loads((problems.DATASET / "bugs.json").read_text())
    kinds = {b["problem"]: b["kind"] for b in bugs}
    hard = {b["problem"] for b in bugs if b["tier"] == "hard"}
    only = lambda exp: [r for r in runs if r["experiment"] == exp]
    scale_rows, pin_rows = only("scale"), only("pinning")  # randomised design only; v1 kept out
    scale_preset, pin_preset = ("full" if scale_rows else "none"), ("full" if pin_rows else "none")
    hunt_rows_raw, hunt_preset = section(runs, "hunt")
    gallery_path = R / "bugs" / "gallery.json"
    gallery = json.loads(gallery_path.read_text()) if gallery_path.exists() else []

    hv = hunt_values(hunt_rows_raw)
    hunt = hunt_section(hv, kinds)
    tests = hunt_tests_section(hv, "exploratory") + hunt_tests_section(hunt_values(only("hunt-focus")), "confirmatory", 10000)
    for fam in ("exploratory", "confirmatory"):
        rows = [t for t in tests if t["family"] == fam]
        for row, ph in zip(rows, holm([t["p_raw"] for t in rows])):
            row["p_holm"] = num(ph)
    base = next((r["tests_median"] for r in hunt if (r["problem"], r["strategy"], r["workers"]) == ("range_add_range_min", "noshare", 8)), None)
    counts = defaultdict(int)
    for r in runs:
        counts[r["experiment"]] += 1
    scale = scale_section(scale_rows, read_csv(R / "pool_bench.csv"))
    pinning, shrink = pinning_section(pin_rows), shrink_section(gallery, read_csv(R / "shrink_scaling.csv"))
    summary = dict(
        meta=dict(generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), commits=commits,
                  runs_per_experiment=dict(sorted(counts.items())),
                  preset={k: v for k, v in (("scale", scale_preset), ("hunt", hunt_preset), ("pinning", pin_preset))
                          if v != "none"},  # sections without data are left out (footnote would mislabel them)
                  strategy_colors=STRATEGY_COLORS, headline=headline(scale, pinning, shrink, len(bugs))),
        scale=scale, order_effect=order_effect_section(only("scale-full-v1"), scale_rows),
        hunt=hunt, hunt_tests=tests, hunt_time_scaling=hunt_time_scaling(hunt, hard),
        power=power_section(base) if base else None, pinning=pinning, shrink=shrink, llm=llm_section(shrink))
    (R / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(f"wrote results/summary.json: {len(summary['scale'])} scale rows, {len(hunt)} hunt rows, "
          f"{len(summary['hunt_tests'])} hunt tests, presets {summary['meta']['preset']}")


if __name__ == "__main__":
    raise SystemExit(main())
