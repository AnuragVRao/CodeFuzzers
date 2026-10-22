#!/usr/bin/env python3
"""Per-upload analysis pipeline: build -> validate -> calibrate -> hunt -> shrink | clean bound -> llm -> sweep -> compare.
Usage: python3 tools/analyze.py <job_dir>
<job_dir> holds gen.cpp, ref.cpp, sol.cpp, optional checker.cpp and config.json:
  {"gen_template": "{seed} {size}", "checker": "exact"|"custom", "budget_s": 60|180|600, "workers": 20, "llm_model": "qwen3:8b"}
Writes progress.jsonl (one event per line: t, stage, status start|done|fail|skip|info, message, data) and report.json
into <job_dir>; everything else (build/, bug/, shrunk/, tmp/) stays there too. Exit 0 = analysis completed (bug or
no bug), 1 = a stage failed. The time plan is fixed at the start: the hunt gets budget - elapsed - reserves (min 10 s);
time a stage does not use is not handed to another stage. Sweep and compare cap sizes at SCALE_MAX_SIZE
so they fit their reserves.
"""
import json, os, shutil, statistics, subprocess, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import llm, problems, shrink
from run import CPU_ORDER

ROOT, FUZZER, RUNTIME = problems.ROOT, problems.ROOT / "build" / "fuzzer", problems.ROOT / "build" / "fs_runtime.o"
RESERVES = dict(shrink=20, llm=30, sweep=20, compare=15)
EVAL_NOTE = "in our evaluation, qwen3:8b located 7/29 planted bugs within ±3 lines (chance ≈ 7%)"
BATTERY_WARNING = "Running on battery: throughput figures can be ~30% lower than when plugged in (measured on this laptop)."
CAL_MS, CAL_BYTES, CAL_MAX_EXP = 50, 1_000_000, 20
SCALE_MAX_SIZE = 200  # sweep / compare measure throughput, not bug finding: keep their tests cheap


class StageFail(Exception):
    pass


class Job:
    def __init__(self, d):
        self.d, self.t0, self.report, self.warnings, self.durations = Path(d), time.time(), {}, [], {}
        for old in ("bug", "shrunk"):
            shutil.rmtree(self.d / old, ignore_errors=True)  # leftovers of an earlier run
        self.log = open(self.d / "progress.jsonl", "w")
        self.cfg = json.loads((self.d / "config.json").read_text())
        self.template = self.cfg.get("gen_template", "{seed} {size}")
        self.model = self.cfg.get("llm_model", "qwen3:8b")
        self.W, self.budget = int(self.cfg.get("workers", 20)), float(self.cfg["budget_s"])
        self.cpus = ",".join(map(str, CPU_ORDER[:self.W]))
        self.max_size_flag = 1  # the fuzzer needs a --max-size; seed-only generators ignore sizes

    def ev(self, stage, status, message="", data=None):
        self.log.write(json.dumps(dict(t=round(time.time() - self.t0, 2), stage=stage, status=status, message=message, data=data)) + "\n")
        self.log.flush()

    def stage(self, name, fn, *args):
        """Run fn(*args) as a stage: start / done events and duration; StageFail -> fail event, re-raised."""
        self.ev(name, "start")
        t = time.time()
        try:
            r = fn(*args)
        except StageFail as e:
            self.ev(name, "fail", str(e))
            raise
        finally:
            self.durations[name] = round(time.time() - t, 2)
        self.ev(name, "done", f"{self.durations[name]} s")
        return r

    def fuzz_cmd(self, out, *flags):
        return [str(FUZZER), "--build", str(self.d / "build"), "--fast", "sol", "--variants", "1", "--checker", self.cfg["checker"],
                "--max-size", str(self.max_size_flag), "--gen-template", self.template, "--out", str(out), *map(str, flags)]

    def fuzz(self, out, *flags, timeout):
        """Run build/fuzzer to completion; returns the parsed JSON summary."""
        r = subprocess.run(self.fuzz_cmd(out, *flags), capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise StageFail(f"fuzzer failed (exit {r.returncode}): {r.stderr[-500:]}")
        return json.loads(Path(out).read_text())


def environment():
    states = []
    for f in Path("/sys/class/power_supply").glob("*/online"):
        try:
            states.append(f.read_text().strip())
        except OSError:
            pass
    power = "unknown" if not states else "ac" if "1" in states else "battery"
    cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), "unknown")
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return dict(power=power, cpu=cpu, git_commit=commit)


def ollama_ok(model):
    try:
        tags = json.loads(urllib.request.urlopen(f"{llm.URL}/api/tags", timeout=3).read())
        return any(m["name"] == model for m in tags["models"])
    except Exception:
        return False


def plan(job, llm_up):
    small = job.budget <= 60
    sweep = [1, job.W] if small else sorted({1, 2, 4, 8, job.W})
    return dict(budget_s=job.budget, reserves=dict(RESERVES, llm=RESERVES["llm"] if llm_up else 0),
                sweep_workers=[w for w in sweep if w <= job.W] or [1], compare_repeats=2 if small else 3)


# ---------------------------------------------------------------- stages
def build(job):
    d, b = job.d, job.d / "build"
    b.mkdir(exist_ok=True)
    custom = job.cfg["checker"] == "custom"
    cov = ["-fsanitize-coverage=trace-pc", "-no-pie"]
    targets = [("gen", "gen.cpp", []), ("ref", "ref.cpp", []), ("fast_sol", "sol.cpp", cov)] + ([("checker", "checker.cpp", [])] if custom else [])
    for _, src, _ in targets:
        if not (d / src).exists():
            raise StageFail(f"missing file {src}")
    if not RUNTIME.exists() or not FUZZER.exists():
        raise StageFail("build/fuzzer or build/fs_runtime.o missing: run tools/build.py first")

    def compile_one(t):
        name, src, extra = t
        cmd = ["g++", "-O2", "-std=c++17", "-w", "-I", str(ROOT / "Dataset/common"), "-I", str(d), *extra, "-o", str(b / name), str(d / src), str(RUNTIME)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return src, "compilation timed out after 60 s"
        return src, None if r.returncode == 0 else "\n".join(r.stderr.splitlines()[:30])

    with ThreadPoolExecutor(len(targets)) as ex:
        errors = [(s, e) for s, e in ex.map(compile_one, targets) if e]
    if errors:
        raise StageFail("\n".join(f"[{s}]\n{e}" for s, e in errors)[:6000])
    return dict(gen=str(b / "gen"), ref=str(b / "ref"), fast=str(b / "fast_sol"), checker=str(b / "checker") if custom else None,
                checker_kind=job.cfg["checker"], gen_template=job.template, max_size=None, build_dir=str(b))


def gen_out(bundle, seed, size):
    try:
        r = subprocess.run([bundle["gen"], *problems.gen_args(bundle["gen_template"], seed, size)], capture_output=True, timeout=10)
        return r.returncode, r.stdout
    except subprocess.TimeoutExpired:
        return None, b""


def validate(job, bundle):
    sized = "{size}" in job.template.split()
    s10 = 10 if sized else None
    if any(gen_out(bundle, s, s10) != gen_out(bundle, s, s10) for s in range(1, 6)):
        raise StageFail("generator is not deterministic for a fixed seed")
    bad = sum(gen_out(bundle, s, s10)[0] != 0 for s in range(1, 21))
    if bad > 10:
        raise StageFail(f"generator exits non-zero on {bad}/20 seeds")
    mode, reason = "seed-only", "template has no {size}"
    if sized:
        ratios = [len(gen_out(bundle, s, 200)[1]) / max(len(gen_out(bundle, s, 5)[1]), 1) for s in range(1, 6)]
        if statistics.median(ratios) >= 2:
            mode, reason = "full", None
        else:  # sizes make no difference: drop {size} so the fuzzer and shrinker treat it as seed-only
            reason = "generator output does not grow with {size}"
            job.template = bundle["gen_template"] = " ".join(t for t in job.template.split() if t != "{size}")
    outcomes = {}
    for s in range(1, 21):
        o = problems.run_test_bundle(bundle, 10 if mode == "full" else None, s)[0]
        outcomes[o] = outcomes.get(o, 0) + 1
    if outcomes.get("invalid", 0) > 4:
        raise StageFail("reference fails on most inputs")
    return dict(mode=mode, reason=reason, smoke=outcomes)


def ref_test(bundle, size, seed, tmp):
    """gen -> file, ref timed -> ("skip"|"invalid"|"ok", ms, input bytes)."""
    inp = tmp / "cal.in"
    with open(inp, "wb") as f:
        try:
            rc = subprocess.run([bundle["gen"], *problems.gen_args(bundle["gen_template"], seed, size)], stdout=f,
                                stderr=subprocess.DEVNULL, timeout=10).returncode
        except subprocess.TimeoutExpired:
            rc = None
    if rc != 0:
        return "skip", 0, 0
    t = {}
    ok = problems._run([bundle["ref"]], inp, tmp / "cal.out", t, "ms") == 0
    return ("ok" if ok else "invalid"), t["ms"], inp.stat().st_size


def calibrate(job, bundle, mode):
    tmp = problems.TMP
    tmp.mkdir(parents=True, exist_ok=True)
    if mode == "seed-only":
        ms = [r[1] for r in (ref_test(bundle, None, s, tmp) for s in range(1, 11)) if r[0] == "ok"]
        med = statistics.median(ms) if ms else 0
        if med > 500:
            job.warnings.append(f"reference takes {med:.0f} ms per input at the generator's own sizes (> 500 ms): the hunt will be slow")
        return dict(max_size=None, table=[dict(size=None, ref_median_ms=round(med, 2))])
    table, max_size = [], 1
    for e in range(CAL_MAX_EXP + 1):
        size = 2 ** e
        rs = [ref_test(bundle, size, s, tmp) for s in range(1, 6)]
        good = [r[1] for r in rs if r[0] == "ok"]
        med, top = (statistics.median(good) if good else 0), max(r[2] for r in rs)
        table.append(dict(size=size, ref_median_ms=round(med, 2), input_bytes=top))
        job.ev("calibrate", "info", f"size {size}: ref {med:.1f} ms, {top} bytes")
        if med > CAL_MS or top > CAL_BYTES or any(r[0] == "invalid" for r in rs):
            break
        max_size = size
    return dict(max_size=max_size, table=table)


def hunt(job, budget):
    out, t0 = job.d / "hunt.json", time.time()
    cmd = job.fuzz_cmd(out, "--mode", "hunt", "--strategy", "rwlock", "--recipes", "guided", "--workers", job.W, "--cpus", job.cpus,
                       "--time-limit", budget, "--bug-dir", job.d / "bug")
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
    while True:
        try:
            p.wait(timeout=2)
            break
        except subprocess.TimeoutExpired:
            el = time.time() - t0
            job.ev("hunt", "info", f"{el:.0f} s / {budget:.0f} s", dict(elapsed=round(el, 1), budget=round(budget, 1)))
            if el > budget + 30:
                p.kill()
                raise StageFail("fuzzer did not stop within its time limit")
    if p.returncode != 0:
        raise StageFail(f"fuzzer failed (exit {p.returncode}): {p.stderr.read()[-500:]}")
    return json.loads(out.read_text())


def first_diff_token(ref, fast):
    r, f = ref.split(), fast.split()
    return next((i + 1 for i in range(max(len(r), len(f))) if r[i:i + 1] != f[i:i + 1]), None)


def do_shrink(job, bundle):
    bug = job.d / "bug"
    r = dict(l.split(None, 1) for l in (bug / "recipe.txt").read_text().splitlines() if l.strip())
    recipe = dict(variant=int(r["variant"]), size=int(r["size"]), seed=int(r["seed"]))
    original = (bug / "input.txt").read_text(errors="replace")
    best, trace, used = shrink.shrink_bundle(bundle, dict(recipe, input=original), job.W, 4000, RESERVES["shrink"], 7)
    outcome, ref_out, fast_out = problems.check_text(bundle, best["input"])
    if outcome not in problems.BUGS:  # inputs come from the generator, so only a flaky solution gets here
        job.warnings.append(f"shrunk input did not reproduce the failure ({outcome}); reporting the original")
        best = dict(recipe, input=original)
        outcome, ref_out, fast_out = problems.check_text(bundle, original)
    ref_s, fast_s = ref_out.decode(errors="replace"), fast_out.decode(errors="replace")
    sd = job.d / "shrunk"
    sd.mkdir(exist_ok=True)
    for name, text in (("input.txt", best["input"]), ("ref_out.txt", ref_s), ("fast_out.txt", fast_s)):
        (sd / name).write_text(text)
    sized = "{size}" in bundle["gen_template"].split()
    bug_block = dict(kind=outcome, confirmed=outcome in problems.BUGS, trace=trace, tests_used=used,
                     original=dict(size=recipe["size"] if sized else None, **shrink.stats(original)),
                     shrunk=dict(size=best["size"] if sized else None, seed=best["seed"], **shrink.stats(best["input"])),
                     first_diff_token=first_diff_token(ref_s, fast_s) if outcome == "WA" else None,
                     input=best["input"][:20000], ref_out=ref_s[:20000], fast_out=fast_s[:20000])
    return bug_block, best, ref_s, fast_s


def clean_bound(h, max_size):
    n = h["outcomes"]["ok"]
    upper = 1 - 0.05 ** (1 / n) if n else 1.0
    where = f"sizes 1–{max_size}" if max_size else "the generator's own sizes"
    return dict(tests=n, upper95=upper, sizes=where,
                sentence=f"No failing input found in {n} tests. With 95% confidence, fewer than {100 * upper:.2g}% of inputs from this generator ({where}) expose a bug.")


def run_llm(job, best, ref_s, fast_s):
    """-> (result or None, skip reason). The model gets 60 s; a late answer is dropped."""
    box = {}

    def work():
        try:
            box["r"] = llm.explain_one((job.d / "sol.cpp").read_text(), best["input"], ref_s, fast_s, job.model)
        except Exception as e:  # network / model errors are not a failed analysis
            box["err"] = str(e)

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(60)
    if t.is_alive():
        return None, "model did not answer within 60 s"
    if "err" in box:
        return None, f"Ollama error: {box['err'][:200]}"
    r = box["r"]
    if r["status"] != "ok":
        return None, f"no usable answer ({r['status']})"
    return dict(model=job.model, label="unverified suggestion", latency_s=r["latency_s"], evaluation_note=EVAL_NOTE,
                answer={k: r[k] for k in ("line", "category", "explanation", "fix")}), None


def sweep(job, ws):
    rows = []
    for w in ws:
        h = job.fuzz(job.d / "sweep.json", "--mode", "scale", "--strategy", "noshare", "--recipes", "random", "--workers", w, "--tests", 1000 * w,
                     "--cpus", ",".join(map(str, CPU_ORDER[:w])), "--seed", 1, timeout=RESERVES["sweep"] * 3 + 30)
        rows.append(dict(workers=w, tests_per_sec=h["tests_per_sec"]))
        job.ev("sweep", "info", f"{w} workers: {h['tests_per_sec']:.0f} tests/s")
    for r in rows:
        r["speedup"] = round(r["tests_per_sec"] / rows[0]["tests_per_sec"], 2)
        r["efficiency"] = round(r["speedup"] / r["workers"], 2)
    return rows


def compare(job, repeats):
    tps = {"noshare": [], "rwlock": []}
    for r in range(repeats):
        for s in (["noshare", "rwlock"] if r % 2 == 0 else ["rwlock", "noshare"]):
            h = job.fuzz(job.d / "compare.json", "--mode", "scale", "--strategy", s, "--recipes", "random", "--workers", job.W, "--tests", 1000 * job.W,
                         "--cpus", job.cpus, "--seed", 100 + r, timeout=RESERVES["compare"] * 3 + 30)
            tps[s].append(h["tests_per_sec"])
    med = {s: statistics.median(v) for s, v in tps.items()}
    return dict(workers=job.W, repeats=repeats, tests_per_sec=tps, median=med, ratio_rwlock_vs_noshare=round(med["rwlock"] / med["noshare"], 3),
                note="differences under ~5% are within run-to-run noise")


# ---------------------------------------------------------------- driver
def analyze(job):
    rep, st = job.report, job.stage
    rep["config"] = job.cfg
    rep["environment"] = env = environment()
    if env["power"] == "battery":
        job.warnings.append(BATTERY_WARNING)
    llm_up = ollama_ok(job.model)
    rep["plan"] = pl = plan(job, llm_up)
    problems.TMP = job.d / "tmp"

    bundle = st("build", build, job)
    v = st("validate", validate, job, bundle)
    rep["mode"] = dict(v, gen_template=job.template)
    cal = st("calibrate", calibrate, job, bundle, v["mode"])
    rep["calibration"], bundle["max_size"] = cal, cal["max_size"]
    job.max_size_flag = cal["max_size"] or 1

    budget = max(10, job.budget - (time.time() - job.t0) - sum(pl["reserves"].values()))
    pl["hunt_budget_s"] = round(budget, 1)
    h = st("hunt", hunt, job, budget)
    rep["hunt"] = dict(tests=h["tests"], tests_per_sec=h["tests_per_sec"], outcomes=h["outcomes"], cov_features=h["cov_features"], first_bug=h.get("first_bug"))
    if h.get("first_bug"):
        rep["bug"], best, ref_s, fast_s = st("shrink", do_shrink, job, bundle)
        if llm_up:
            job.ev("llm", "start")
            rep["llm"], why = run_llm(job, best, ref_s, fast_s)
            job.ev("llm", "done" if rep["llm"] else "skip", why or "")
        else:
            rep["llm"] = None
            job.ev("llm", "skip", f"Ollama or model {job.model} not available")
    else:
        rep["clean_bound"] = st("clean", clean_bound, h, cal["max_size"])
        job.ev("clean", "info", rep["clean_bound"]["sentence"])
    job.max_size_flag = pl["scale_max_size"] = min(job.max_size_flag, SCALE_MAX_SIZE)
    rep["sweep"] = st("sweep", sweep, job, pl["sweep_workers"])
    rep["compare"] = st("compare", compare, job, pl["compare_repeats"])


def main():
    job = Job(sys.argv[1])
    failed = None
    try:
        analyze(job)
    except StageFail as e:
        failed = str(e)
    except Exception as e:  # unexpected: still leave a report behind
        failed = f"internal error: {e!r}"
        job.ev("pipeline", "fail", failed)
    shutil.rmtree(job.d / "tmp", ignore_errors=True)
    job.report.update(status="failed" if failed else "completed", failure=failed, warnings=job.warnings,
                      stage_durations=job.durations, wall_s=round(time.time() - job.t0, 2))
    (job.d / "report.json").write_text(json.dumps(job.report, indent=1) + "\n")
    job.ev("pipeline", "fail" if failed else "done", job.report["status"])
    return 1 if failed else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)  # a daemon LLM thread may still be waiting on the network
