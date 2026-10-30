#!/usr/bin/env python3
"""Builds everything the fuzzer needs into build/, in parallel, skipping up-to-date targets.
build/fs_runtime.o (no coverage) is linked into every problem binary. Per problem in build/<name>/:
  lightweight (-O2): gen, gen_alt (if variant exists), ref, checker, verifier (plain, exit 0 = valid
  input on stdin);  path-tracking (-O2 trace-pc,
  -no-pie): fast_sol, fast_bug.  Also smoke, pool_bench(_tsan), fuzzer(_tsan), tests/* (tape_test_<group>:
  core/tests/tape_test.cpp around one real generator, no runtime).
Rebuilds when a target is older than its listed deps (problem binaries: source, fs_runtime.o and every header
it may include, see problems.header_deps); --force rebuilds everything.
"""
import argparse, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import problems

ROOT = problems.ROOT
BUILD, CORE = ROOT / "build", ROOT / "core"
RUNTIME = BUILD / "fs_runtime.o"
COV = ["-fsanitize-coverage=trace-pc", "-no-pie"]
# core/tests/tape_test.cpp is built once per group around one real generator (tape_test_<group>)
TAPE_TESTS = {"arrays": "majority_voting", "strings": "longest_common_substring",
              "graphs": "connected_components_of_complement_graph"}
CXX = ["g++", "-std=c++17"]
FORCE = False


def build(out, cmd, deps):
    """Run cmd unless out is newer than every dep. Returns ("built"|"up-to-date"|"failed", out, err)."""
    if not FORCE and out.exists() and all(out.stat().st_mtime > Path(d).stat().st_mtime for d in deps):
        return "up-to-date", out, ""
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        return "built", out, ""
    lines = r.stderr.splitlines()
    return "failed", out, next((l for l in lines if "error" in l), lines[0] if lines else "?")


def problem_targets(p):
    d, out = p["dir"], BUILD / p["name"]
    fl = problems.flags(d)
    srcs = {"gen": d / "gen/generator.cpp", "ref": d / "brute.cpp", "checker": d / "checker.cpp"}
    hdr = lambda src: [src, *problems.header_deps(src, fl)]
    jobs = [(out / "verifier", ["g++", *fl, "-o", str(out / "verifier"), str(d / "verifier.cpp")], hdr(d / "verifier.cpp"))]
    if "generator_alt_1" in p["variants"]:
        srcs["gen_alt"] = d / "gen/generator_alt_1.cpp"
    jobs += [(out / name, ["g++", *fl, "-o", str(out / name), str(src), str(RUNTIME)], [*hdr(src), RUNTIME])
             for name, src in srcs.items()]
    for name, src in (("fast_sol", d / "sol.cpp"), ("fast_bug", d / "sol_bug.cpp")):
        jobs.append((out / name, ["g++", *fl, *COV, "-o", str(out / name), str(src), str(RUNTIME)], [*hdr(src), RUNTIME]))
    return jobs


def tool_targets():
    def exe(out, src, flags, deps, runtime=False):
        cmd = [*CXX, *flags, "-o", str(out), str(src)] + ([str(RUNTIME)] if runtime else [])
        return out, cmd, [src, *deps] + ([RUNTIME] if runtime else [])
    srv, pool, cmp_, arena = CORE / "server.hpp", CORE / "pool.hpp", CORE / "compare.hpp", CORE / "arena.hpp"
    t = CORE / "tests"
    jobs = [exe(BUILD / "smoke", CORE / "smoke.cpp", ["-O2"], [srv, cmp_]),
            exe(BUILD / "pool_bench", CORE / "pool_bench.cpp", ["-O2", "-pthread"], [pool]),
            exe(BUILD / "pool_bench_tsan", CORE / "pool_bench.cpp", ["-fsanitize=thread", "-g", "-O1", "-pthread"], [pool]),
            exe(BUILD / "tests/server_test", t / "server_test.cpp", ["-O2"], [srv]),
            exe(BUILD / "tests/checker_test", t / "checker_test.cpp", ["-O2"], [srv, cmp_]),
            exe(BUILD / "tests/tape_server_test", t / "tape_server_test.cpp", ["-O2"], [srv]),
            exe(BUILD / "tests/tape_replay_check", t / "tape_replay_check.cpp", ["-O2"], [srv, cmp_]),
            exe(BUILD / "tests/gen_tape_toy", t / "gen_tape_toy.cpp", ["-O2", "-I", str(problems.DATASET / "common")],
                [problems.DATASET / "common/random.h"], runtime=True),
            exe(BUILD / "fuzzer", CORE / "fuzzer.cpp", ["-O2", "-pthread"], [srv, pool, cmp_, arena]),
            exe(BUILD / "fuzzer_tsan", CORE / "fuzzer.cpp", ["-fsanitize=thread", "-g", "-O1", "-pthread"], [srv, pool, cmp_, arena]),
            exe(BUILD / "tests/arena_test", t / "arena_test.cpp", ["-O2", "-pthread"], [arena, pool, srv]),
            exe(BUILD / "tests/arena_test_tsan", t / "arena_test.cpp", ["-fsanitize=thread", "-g", "-O1", "-pthread"], [arena, pool, srv])]
    jobs += [exe(BUILD / "tests" / n, t / f"{n}.cpp", ["-O2"], [], runtime=True) for n in ("crash", "hang", "exit3", "exit_code", "gen_named", "gen_seedonly")]
    for group, name in TAPE_TESTS.items():
        d = problems.get(name)["dir"]
        jobs.append(exe(BUILD / "tests" / f"tape_test_{group}", t / "tape_test.cpp",
                        [*problems.flags(d), f'-DCF_GEN_SRC="{d / "gen/generator.cpp"}"'],
                        problems.header_deps(d / "gen/generator.cpp", problems.flags(d)) + [d / "gen/generator.cpp"]))
    return jobs


def main():
    global FORCE
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild everything")
    FORCE = ap.parse_args().force
    rt = CORE / "fs_runtime.cpp"
    results = [build(RUNTIME, [*CXX, "-O2", "-c", "-o", str(RUNTIME), str(rt)], [rt])]
    if results[0][0] == "failed":
        print(f"fs_runtime.o failed: {results[0][2]}")
        return 1
    jobs = tool_targets()
    for p in problems.load():
        jobs += problem_targets(p)
    with ThreadPoolExecutor() as ex:
        results += list(ex.map(lambda j: build(*j), jobs))

    count = {k: sum(r[0] == k for r in results) for k in ("built", "up-to-date", "failed")}
    print(f"{count['built']} built, {count['up-to-date']} up-to-date, {count['failed']} failed")
    for status, out, err in results:
        if status == "failed":
            print(f"  {out.relative_to(ROOT)}: {err}")
    return 1 if count["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
