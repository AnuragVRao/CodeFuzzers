#!/usr/bin/env python3
"""Aggregates all results into results/summary.json. Run tools/flatten.py first.
Inputs: results/runs.csv, results/pool_bench.csv, results/shrink_scaling.csv, results/bugs/gallery.json,
Dataset/bugs.json. Full-preset experiments are used; if one has no rows, its *-quick twin is used.
Formulas (tps = tests_per_sec; medians and quartiles over the repeats of one configuration):
  speedup_abs    = tps_median / tps_median(noshare, same problem/K/F, workers=1)
  speedup_rel    = tps_median / tps_median(same strategy/problem/K/F, workers=1)
  efficiency_abs = speedup_abs / workers
  vs_noshare     = tps_median / tps_median(noshare, same problem/K/F/workers)
  predicted_tps  = min(noshare tps_median at this W, pool_bench tests_per_sec at this strategy/K/F/threads)
  hunt censoring = a run without a bug counts as +inf tests/time; a quantile touching +inf -> null + flag
  hunt_tests     = two-sided Mann-Whitney U on tests-to-bug (censored = +inf); p_holm = Holm over all rows
  ratio          = median_b / median_a (null if either median is censored)
  hunt_time_scaling = geometric mean over problems of time_median (censored medians skipped and counted)
  pinning ratio  = median(pinned tps) / median(unpinned tps);  shrink speedup = median wall(W=1) / median wall(W)
Usage: python3 tools/aggregate.py
"""
import csv, json, math, sys, warnings
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np
from scipy.stats import mannwhitneyu
import problems

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
    g = defaultdict(list)
    for r in rows:
        g[(r["problem"], r["strategy"], int(r["K"]), float(r["F"]), int(r["workers"]))].append(float(r["tests_per_sec"]))
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
                        vs_noshare=num(m / nsw),
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
                 **qstats(t, "tests"), **qstats(tm, "time"))
            for (p, s, w), (t, tm) in sorted(g.items())]


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, running = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = running
    return adj


def hunt_tests_section(g):
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
            out.append(dict(problem=p, workers=w, comparison=comparison, a=a, b=b, median_a=num(ma), median_b=num(mb),
                            ratio=num(mb / ma) if math.isfinite(ma) and math.isfinite(mb) and ma > 0 else None,
                            p_raw=num(pr if math.isfinite(pr) else 1.0)))
    for row, ph in zip(out, holm([r["p_raw"] for r in out])):
        row["p_holm"] = num(ph)
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


def shrink_section(gallery, scaling):
    rows = [dict(problem=g["problem"], tier=g["tier"], size_original=g["original"]["size"], size_shrunk=g["shrunk"]["size"],
                 bytes_original=g["original"]["bytes"], bytes_shrunk=g["shrunk"]["bytes"],
                 tests_used=g["tests_used"], wall_s=g["wall_s"]) for g in gallery if "shrunk" in g]
    g = defaultdict(list)
    for r in scaling:
        g[(r["problem"], int(r["workers"]))].append(float(r["wall_s"]))
    sc = []
    for (p, w), v in sorted(g.items()):
        base = quant(g[(p, 1)], 50) if (p, 1) in g else math.nan
        sc.append(dict(problem=p, workers=w, n=len(v), wall_median=num(quant(v, 50)), speedup=num(base / quant(v, 50))))
    return dict(gallery=rows, scaling=sc)


def main():
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
    scale_rows, scale_preset = section(runs, "scale")
    hunt_rows_raw, hunt_preset = section(runs, "hunt")
    pin_rows, pin_preset = section(runs, "pinning")
    gallery_path = R / "bugs" / "gallery.json"
    gallery = json.loads(gallery_path.read_text()) if gallery_path.exists() else []

    hv = hunt_values(hunt_rows_raw)
    hunt = hunt_section(hv, kinds)
    counts = defaultdict(int)
    for r in runs:
        counts[r["experiment"]] += 1
    summary = dict(
        meta=dict(generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), commits=commits,
                  runs_per_experiment=dict(sorted(counts.items())),
                  preset=dict(scale=scale_preset, hunt=hunt_preset, pinning=pin_preset)),
        scale=scale_section(scale_rows, read_csv(R / "pool_bench.csv")),
        hunt=hunt, hunt_tests=hunt_tests_section(hv), hunt_time_scaling=hunt_time_scaling(hunt, hard),
        pinning=pinning_section(pin_rows), shrink=shrink_section(gallery, read_csv(R / "shrink_scaling.csv")))
    (R / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(f"wrote results/summary.json: {len(summary['scale'])} scale rows, {len(hunt)} hunt rows, "
          f"{len(summary['hunt_tests'])} hunt tests, presets {summary['meta']['preset']}")


if __name__ == "__main__":
    main()
