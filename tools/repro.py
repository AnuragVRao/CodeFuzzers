#!/usr/bin/env python3
"""Re-checks a bug recorded by build/fuzzer, without any fork server.
Usage: python3 tools/repro.py <problem> <bug-dir>
Regenerates the input from <bug-dir>/recipe.txt and checks it equals input.txt, then runs ref
(brute) and fast_bug from build/<problem>/ directly on input.txt and compares them with the
problem's rule (exact tokens or checker). Prints both outputs and the verdict.
"""
import subprocess, sys, tempfile
from pathlib import Path
import problems

TIMEOUT = 5


def run(cmd, stdin_path):
    with open(stdin_path, "rb") as f:
        try:
            r = subprocess.run(cmd, stdin=f, capture_output=True, timeout=TIMEOUT)
            return r.returncode, r.stdout
        except subprocess.TimeoutExpired:
            return None, b""


def show(label, rc, out, limit=15):
    lines = out.decode(errors="replace").splitlines()
    print(f"--- {label}: exit={'TIMEOUT' if rc is None else rc}, {len(lines)} lines")
    for l in lines[:limit]:
        print("   ", l)
    if len(lines) > limit:
        print(f"    ... ({len(lines) - limit} more)")


def main():
    name, bug_dir = sys.argv[1], Path(sys.argv[2])
    p = next(x for x in problems.load() if x["name"] == name)
    b = problems.ROOT / "build" / name
    inp = bug_dir / "input.txt"
    recipe = dict(l.split(None, 1) for l in (bug_dir / "recipe.txt").read_text().splitlines() if l.strip())
    print(f"recipe: {recipe}")

    gen = b / ("gen_alt" if recipe["variant"].strip() == "1" else "gen")
    regen = subprocess.run([str(gen), recipe["seed"].strip(), recipe["size"].strip()], capture_output=True).stdout
    print(f"input.txt: {inp.stat().st_size} bytes; regenerated from recipe: {'identical' if regen == inp.read_bytes() else 'DIFFERENT'}")

    rc_ref, out_ref = run([str(b / "ref")], inp)
    rc_fast, out_fast = run([str(b / "fast_bug")], inp)
    show("ref (brute.cpp)", rc_ref, out_ref)
    show("fast_bug (sol_bug.cpp)", rc_fast, out_fast)

    if rc_ref != 0:
        verdict = "INVALID (reference failed)"
    elif rc_fast is None:
        verdict = "MISMATCH: TLE"
    elif rc_fast != 0:
        verdict = "MISMATCH: RE"
    elif p["checker_kind"] == "custom":
        with tempfile.TemporaryDirectory() as t:
            fo, fa = Path(t) / "out", Path(t) / "ans"
            fo.write_bytes(out_fast), fa.write_bytes(out_ref)
            r = subprocess.run([str(b / "checker"), str(inp), str(fo), str(fa)], capture_output=True, text=True)
            verdict = "agree (checker ok)" if r.returncode == 0 else f"MISMATCH: WA (checker: {r.stderr.strip()[:200]})"
    else:
        verdict = "agree" if out_fast.split() == out_ref.split() else "MISMATCH: WA (tokens differ)"
        a, b2 = out_ref.decode().splitlines(), out_fast.decode().splitlines()
        diff = next((i for i in range(max(len(a), len(b2))) if a[i:i + 1] != b2[i:i + 1]), None)
        if diff is not None:
            print(f"first differing line {diff + 1}: ref={a[diff] if diff < len(a) else '<none>'}"
                  f"  fast_bug={b2[diff] if diff < len(b2) else '<none>'}")
    print(f"verdict: {verdict}")
    return 0 if verdict.startswith("MISMATCH") else 1


if __name__ == "__main__":
    raise SystemExit(main())
