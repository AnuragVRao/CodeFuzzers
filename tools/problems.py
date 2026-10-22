"""Problem list from Dataset/manifest.json, a cached g++ helper, and run_test_bundle(): one plain
(non-fork-server) test gen -> ref -> fast -> compare, shared by sanity.py, shrink.py and analyze.py.
A bundle is a dict {gen, ref, fast, checker (path or None), checker_kind ("exact"|"custom"),
gen_template, max_size, build_dir}; bundle_for_problem() makes one from the dataset, tools/analyze.py
makes one from an upload. Dataset plain binaries live in build/plain/<problem>/, compiled on first use.
"""
import functools, json, subprocess, threading, time, uuid
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "Dataset"
GROUPS = {"array": "arrays", "graph": "graphs", "string": "strings"}  # manifest input_type -> folder


def load():
    """Manifest entries plus: group, dir, variants (generator names present in gen/)."""
    out = []
    for p in json.loads((DATASET / "manifest.json").read_text())["problems"]:
        group = GROUPS[p["input_type"]]
        d = DATASET / "problems" / group / p["name"]
        assert d.is_dir(), d
        variants = ["generator"] + (["generator_alt_1"] if (d / "gen/generator_alt_1.cpp").exists() else [])
        out.append(dict(p, group=group, dir=d, variants=variants))
    return out


def flags(pdir, opt="-O2"):
    return [opt, "-std=c++17", "-w", "-I", str(DATASET / "common"), "-I", str(pdir), "-I", str(pdir / "gen")]


def compile(src, out, flags):
    """g++ src -> out, skipped if out is newer than src. Raises on compile error."""
    src, out = Path(src), Path(out)
    if out.exists() and out.stat().st_mtime > src.stat().st_mtime:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["g++", *flags, "-o", str(out), str(src)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"compile failed: {src}\n{r.stderr[-2000:]}")
    return out


PLAIN = ROOT / "build" / "plain"
TMP = Path("/dev/shm/cf_tests")
TIMEOUT = 5
BUGS = ("WA", "RE", "TLE")
_locks = defaultdict(threading.Lock)
_by_name = {}


def get(name):
    if not _by_name:
        _by_name.update((p["name"], p) for p in load())
    return _by_name[name]


def plain_bins(p, fast):
    """Compile (once; thread-safe) and return the plain binaries of problem p."""
    with _locks[p["name"]]:
        out, fl = PLAIN / p["name"], flags(p["dir"])
        bins = {v: compile(p["dir"] / "gen" / f"{v}.cpp", out / v, fl) for v in p["variants"]}
        for name in (fast, "brute", "checker"):
            bins[name] = compile(p["dir"] / f"{name}.cpp", out / name, fl)
    return bins


def _run(cmd, inp, out, times, key):
    """cmd < inp > out. Returns returncode, or None on timeout; stores wall ms in times[key]."""
    t0 = time.perf_counter()
    with open(inp, "rb") as fi, open(out, "wb") as fo:
        try:
            rc = subprocess.run(cmd, stdin=fi, stdout=fo, stderr=subprocess.DEVNULL, timeout=TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            rc = None
    if times is not None:
        times[key] = (time.perf_counter() - t0) * 1000
    return rc


def gen_args(template, seed, size):
    """Fill a generator template; tokens must be exactly {seed}/{size} (size None drops {size})."""
    out = []
    for t in template.split():
        if t == "{seed}":
            out.append(str(seed))
        elif t == "{size}":
            if size is not None:
                out.append(str(size))
        elif "{seed}" in t or "{size}" in t:
            raise ValueError(f"template token {t!r} must be exactly {{seed}} or {{size}}")
        else:
            out.append(t)
    return out


@functools.lru_cache(maxsize=None)
def max_sizes():
    return json.loads((ROOT / "fuzz_config.json").read_text())


def bundle_for_problem(problem, fast="sol", variant=0):
    """Bundle of a dataset problem (name or load() entry); fast: "sol" or "bug"/"sol_bug"."""
    p = get(problem) if isinstance(problem, str) else problem
    fast = "sol_bug" if fast in ("bug", "sol_bug") else "sol"
    bins = plain_bins(p, fast)
    custom = p["checker_kind"] == "custom"
    max_size = max_sizes()[p["name"]]["max_size"]
    return dict(gen=str(bins[p["variants"][variant]]), ref=str(bins["brute"]), fast=str(bins[fast]),
                checker=str(bins["checker"]) if custom else None, checker_kind="custom" if custom else "exact",
                gen_template="{seed} {size}", max_size=max_size, build_dir=str(PLAIN / p["name"]))


def _judge(b, inp, out, ans, times):
    """ref and fast on file inp (outputs to ans / out), then compare -> outcome (not gen_skip)."""
    if _run([b["ref"]], inp, ans, times, "brute_ms") != 0:
        return "invalid"
    rf = _run([b["fast"]], inp, out, times, "fast_ms")
    if rf is None:
        return "TLE"
    if rf != 0:
        return "RE"
    if b["checker_kind"] == "custom":
        same = subprocess.run([b["checker"], str(inp), str(out), str(ans)], capture_output=True).returncode == 0
    else:
        same = out.read_bytes().split() == ans.read_bytes().split()
    return "ok" if same else "WA"


def _temp_files():
    TMP.mkdir(parents=True, exist_ok=True)
    base = TMP / uuid.uuid4().hex
    return [base.with_suffix(x) for x in (".in", ".out", ".ans")]


def run_test_bundle(bundle, size, seed, times=None):
    """One test -> (outcome, input_text); outcome per CLAUDE.md "Outcome of one test".
    size: int or None (dropped from the template); times: optional dict that receives fast_ms / brute_ms."""
    inp, out, ans = _temp_files()
    try:
        with open(inp, "wb") as f:
            try:
                g = subprocess.run([bundle["gen"], *gen_args(bundle["gen_template"], seed, size)], stdout=f,
                                   stderr=subprocess.DEVNULL, timeout=TIMEOUT).returncode
            except subprocess.TimeoutExpired:
                g = None
        if g != 0:
            return "gen_skip", ""
        return _judge(bundle, inp, out, ans, times), inp.read_text(errors="replace")
    finally:
        for f in (inp, out, ans):
            f.unlink(missing_ok=True)


def check_text(bundle, text):
    """Run ref and fast on a given input text -> (outcome, ref_out bytes, fast_out bytes)."""
    inp, out, ans = _temp_files()
    try:
        inp.write_text(text)
        outcome = _judge(bundle, inp, out, ans, None)
        return outcome, (ans.read_bytes() if ans.exists() else b""), (out.read_bytes() if out.exists() else b"")
    finally:
        for f in (inp, out, ans):
            f.unlink(missing_ok=True)


def run_test(problem, variant, size, seed, fast, times=None, gen=None, gen_template="{seed} {size}"):
    """Thin wrapper over run_test_bundle for a dataset problem (name or load() entry); variant: 0/1;
    gen: optional path of another generator binary (e.g. an LLM-written one) used instead;
    gen_template: generator arguments, whole tokens {seed} / {size}."""
    b = bundle_for_problem(problem, fast, variant)
    return run_test_bundle(dict(b, gen=str(gen or b["gen"]), gen_template=gen_template), size, seed, times)
