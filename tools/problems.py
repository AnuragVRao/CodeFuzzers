"""Problem list from Dataset/manifest.json, a cached g++ helper, and run_test(): one plain
(non-fork-server) test gen -> brute -> fast -> compare, shared by sanity.py and shrink.py.
Plain binaries live in build/plain/<problem>/ and are compiled on first use.
"""
import json, subprocess, threading, time, uuid
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


def run_test(problem, variant, size, seed, fast, times=None):
    """One test -> (outcome, input_text); outcome per CLAUDE.md "Outcome of one test".
    problem: name or load() entry; variant: 0/1; size: int or None (generator default);
    fast: "sol" or "bug"/"sol_bug"; times: optional dict that receives fast_ms / brute_ms."""
    p = get(problem) if isinstance(problem, str) else problem
    fast = "sol_bug" if fast in ("bug", "sol_bug") else "sol"
    bins = plain_bins(p, fast)
    TMP.mkdir(parents=True, exist_ok=True)
    base = TMP / uuid.uuid4().hex
    inp, out, ans = (base.with_suffix(x) for x in (".in", ".out", ".ans"))
    try:
        gen_cmd = [str(bins[p["variants"][variant]]), str(seed)] + ([str(size)] if size is not None else [])
        with open(inp, "wb") as f:
            try:
                g = subprocess.run(gen_cmd, stdout=f, stderr=subprocess.DEVNULL, timeout=TIMEOUT).returncode
            except subprocess.TimeoutExpired:
                g = None
        if g != 0:
            return "gen_skip", ""
        text = inp.read_text(errors="replace")
        if _run([str(bins["brute"])], inp, ans, times, "brute_ms") != 0:
            return "invalid", text
        rf = _run([str(bins[fast])], inp, out, times, "fast_ms")
        if rf is None:
            return "TLE", text
        if rf != 0:
            return "RE", text
        if p["checker_kind"] == "custom":
            same = subprocess.run([str(bins["checker"]), str(inp), str(out), str(ans)], capture_output=True).returncode == 0
        else:
            same = out.read_bytes().split() == ans.read_bytes().split()
        return ("ok" if same else "WA"), text
    finally:
        for f in (inp, out, ans):
            f.unlink(missing_ok=True)
