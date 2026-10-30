#!/usr/bin/env python3
"""Replays every first_bug in results/raw/<experiment>/<problem>/*.json (Step 0.2 evidence).
Per run: regenerate the input from (variant, size, seed) with the build/plain/ generator, compare it with
the run's saved <run>/input.txt (the sibling directory, NOT config.bug_dir, which is stale for moved runs,
see docs/known_issues.md issue 4), run ref and fast, then the checker (custom problems: its exit code,
e.g. "checker_rc=3" is testlib _fail) or a token compare (exact problems: "exact_WA").
Read-only on results/raw. Summary (counts per experiment/problem) -> results/derived/v1_first_bug_replay.json.
Usage: python3 tools/replay_first_bugs.py
"""
import json, subprocess, tempfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import problems

RAW = problems.ROOT / "results" / "raw"
OUT = problems.ROOT / "results" / "derived" / "v1_first_bug_replay.json"
TIMEOUT = 10


def run(cmd, stdin_path, out_path):
    """cmd < stdin_path > out_path -> returncode, or None on timeout."""
    with open(stdin_path, "rb") as fi, open(out_path, "wb") as fo:
        try:
            return subprocess.run(cmd, stdin=fi, stdout=fo, stderr=subprocess.DEVNULL, timeout=TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            return None


def replay(path):
    """One run -> (experiment, problem, recorded kind, replay result, saved input matches)."""
    d = json.loads(path.read_text())
    fb = d["first_bug"]
    b = problems.bundle_for_problem(path.parent.name, d["config"]["fast"], fb["variant"])
    with tempfile.TemporaryDirectory(dir="/dev/shm") as t:
        inp, ans, out = Path(t, "in"), Path(t, "ans"), Path(t, "out")
        with open(inp, "wb") as f:
            g = subprocess.run([b["gen"], str(fb["seed"]), str(fb["size"])], stdout=f, timeout=TIMEOUT).returncode
        saved = path.with_suffix("") / "input.txt"
        same_input = saved.exists() and saved.read_bytes() == inp.read_bytes()
        if g != 0:
            res = "gen_skip"
        elif run([b["ref"]], inp, ans) != 0:
            res = "ref_failed"
        else:
            rf = run([b["fast"]], inp, out)
            if rf is None:
                res = "TLE"
            elif rf != 0:
                res = "RE"
            elif b["checker"]:
                res = f"checker_rc={subprocess.run([b['checker'], str(inp), str(out), str(ans)], capture_output=True).returncode}"
            else:
                res = "exact_WA" if out.read_bytes().split() != ans.read_bytes().split() else "exact_ok"
    return path.parent.parent.name, path.parent.name, fb["kind"], res, same_input


def main():
    files = [p for p in sorted(RAW.glob("*/*/*.json")) if json.loads(p.read_text()).get("first_bug")]
    with ThreadPoolExecutor(16) as ex:
        rows = list(ex.map(replay, files))
    table, total = defaultdict(Counter), Counter()
    for exp, prob, kind, res, same in rows:
        c = table[f"{exp}/{prob}"]
        c[res] += 1
        c["same_kind" if res in (f"exact_{kind}", kind) or (kind == "WA" and res == "checker_rc=1") else "other_kind"] += 1
        c["input_match" if same else "input_mismatch"] += 1
    for c in table.values():
        total.update(c)
    summary = dict(runs=len(rows), total=dict(sorted(total.items())),
                   per_experiment_problem={k: dict(sorted(v.items())) for k, v in sorted(table.items())})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=1) + "\n")
    print(f"{len(rows)} v1 runs with a first_bug")
    for k, v in summary["per_experiment_problem"].items():
        print(f"{k:56} " + ", ".join(f"{a}: {n}" for a, n in v.items()))
    print("TOTAL", summary["total"])
    print(f"wrote {OUT.relative_to(problems.ROOT)}")


if __name__ == "__main__":
    main()
