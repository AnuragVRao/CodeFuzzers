#!/usr/bin/env python3
"""Generator-space shrinker: finds a smaller failing recipe (variant, size, seed) for a bug.
Usage: python3 tools/shrink.py <problem> <bug-dir> [--workers W] [--budget 4000] [--seed 7]
Each round the main thread draws 64 candidates (same variant, log-uniform smaller size, fresh
seed), evaluates them in a process pool, and processes results in candidate order, so the outcome is
identical for any W. Writes <bug-dir>/shrunk/{input,recipe,ref_out,fast_out}.txt + info.json.
"""
import argparse, json, math, os, random, subprocess, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import problems, repro
import hashlib, re, shutil, struct, sys  # v2 shrinker (below)

BATCH, PATIENCE = 64, 8
POOL = ProcessPoolExecutor  # evaluator pool (one per shrink, reused every round); threads hit the GIL


def evaluate(job):
    """(bundle, candidate) -> candidate + outcome + input. Top-level so a process pool can pickle it."""
    bundle, c = job
    outcome, text = problems.run_test_bundle(bundle, c["size"], c["seed"])
    return dict(c, outcome=outcome, input=text)


def read_recipe(path):
    r = dict(l.split(None, 1) for l in path.read_text().splitlines() if l.strip())
    return dict(variant=int(r["variant"]), size=int(r["size"]), seed=int(r["seed"]))


def stats(text):
    return dict(bytes=len(text.encode()), lines=len(text.splitlines()))


def nbytes(r):
    return len(r["input"].encode())


def best_of(results, key):
    """Failing result with the smallest key, earliest candidate on ties."""
    failing = [r for r in results if r["outcome"] in problems.BUGS]
    return min(failing, key=key, default=None)


def shrink_bundle(bundle, recipe, workers, budget_tests, wall_limit_s, seed):
    """Smaller failing recipe for a bundle -> (best, trace, tests_used). recipe: variant, size, seed and
    optionally the failing input text (regenerated otherwise). Sized generators: shrink the size.
    Seed-only generators (template without {size}): batches of fresh seeds, keep the failing input with
    the fewest bytes. Results are processed in candidate order, so the outcome is identical for any W
    (unless wall_limit_s cuts a run short)."""
    rng, t0 = random.Random(seed), time.time()
    sized = "{size}" in bundle["gen_template"].split()
    text = recipe.get("input")
    if text is None:
        text = problems.run_test_bundle(bundle, recipe["size"] if sized else None, recipe["seed"])[1]
    best = dict(recipe, input=text)
    measure = (lambda r: r["size"]) if sized else nbytes
    trace, used, rnd, stale = [[0, measure(best)]], 0, 0, 0
    key = lambda r: (r["size"], nbytes(r)) if sized else nbytes(r)

    with POOL(workers) as ex:
        while (not sized or best["size"] > 1) and stale < PATIENCE and used < budget_tests and time.time() - t0 < wall_limit_s:
            rnd += 1
            m = best["size"] - 1 if sized else 0
            n = min(BATCH, budget_tests - used)
            cands = [dict(variant=best["variant"],  # size first, then seed: the historical draw order
                          size=min(m, int(math.exp(rng.uniform(0, math.log(m + 1))))) if sized else None,
                          seed=rng.randrange(1, 2**63)) for _ in range(n)]
            results = list(ex.map(evaluate, [(bundle, c) for c in cands]))  # map() keeps candidate order
            used += len(cands)
            found = best_of(results, key)
            if found and (sized or nbytes(found) < nbytes(best)):
                best, stale = found, 0
            else:
                stale += 1
            trace.append([rnd, measure(best)])
        if sized:  # polish: more seeds at the final size, keep the failing input with the fewest bytes
            cands = [dict(variant=best["variant"], size=best["size"], seed=rng.randrange(1, 2**63)) for _ in range(BATCH)]
            results = list(ex.map(evaluate, [(bundle, c) for c in cands]))
            used += len(cands)
            found = best_of(results, key)
            if found and nbytes(found) < nbytes(best):
                best = found
    return best, trace, used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("problem")
    ap.add_argument("bug_dir", type=Path)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--budget", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    recipe = read_recipe(a.bug_dir / "recipe.txt")
    original = (a.bug_dir / "input.txt").read_text(errors="replace")
    t0 = time.time()
    bundle = problems.bundle_for_problem(a.problem, "bug", recipe["variant"])
    best, trace, used = shrink_bundle(bundle, dict(recipe, input=original), a.workers, a.budget, float("inf"), a.seed)
    wall = time.time() - t0

    out = a.bug_dir / "shrunk"
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.txt").write_text(best["input"])
    (out / "recipe.txt").write_text(f"variant {best['variant']}\nsize {best['size']}\nseed {best['seed']}\n")
    verifier = problems.ROOT / "build" / a.problem / "verifier"
    with open(out / "input.txt", "rb") as f:
        verifier_ok = subprocess.run([str(verifier)], stdin=f, capture_output=True).returncode == 0
    c = repro.check_input(a.problem, out / "input.txt")
    (out / "ref_out.txt").write_bytes(c["out_ref"])
    (out / "fast_out.txt").write_bytes(c["out_fast"])
    info = dict(problem=a.problem,
                original=dict(size=recipe["size"], seed=recipe["seed"], **stats(original)),
                shrunk=dict(size=best["size"], seed=best["seed"], **stats(best["input"])),
                trace=trace, tests_used=used, workers=a.workers, wall_s=round(wall, 3),
                verifier_ok=verifier_ok, mismatch_ok=c["verdict"].startswith("MISMATCH"))
    (out / "info.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"{a.problem}: size {recipe['size']} -> {best['size']}, bytes {info['original']['bytes']} -> "
          f"{info['shrunk']['bytes']}, {used} tests, {wall:.1f}s, verifier_ok={verifier_ok}, "
          f"mismatch_ok={info['mismatch_ok']} ({c['verdict']})")
    return 0 if verifier_ok and info["mismatch_ok"] else 1



# ---------------------------------------------------------------------------------------------------------------
# v2 shrinker (roadmap Step S, docs/shrink_plan.md): the default of this CLI; the generator-space shrinker above is
# the old one, kept unchanged behind --old.
#   python3 tools/shrink.py <problem> <bug-dir> --out DIR [--max-evals 2000] [--wall 60]
# Reads <bug-dir>/input.txt, recipe.txt and (pilot tape bugs) tape.bin; writes only to DIR (input.txt, info.json).
# Predicate: the candidate's verdict equals the original's, which must be WA: verifier OK, ref and sol_bug exit 0,
# then the checker exits exactly 1 (custom checker) or the outputs have equal token counts and differ (exact).
# Stage 0 capture: build/tape/ generator (tape.bin or an empty tape + the recipe's seed and size); its output must
# hash to input.txt. Stage 1 (tape, fallback_zero on): truncate, delete spans of 8/4/2/1 words, zero draws, reduce
# draws, repeated until a pass accepts nothing. Stage 2: line-level then token-level (per line) ddmin on the text.
# Deterministic (no randomness); every candidate costs one evaluation unless memoised. Best = fewest tokens, then
# bytes, then earliest. A budget stop (evaluation cap, wall time) keeps the best so far.
# S2 (default; --s1 runs the S1 shrinker above unchanged, docs/shrink_plan_s2.md): a count-aware pass (stage 3)
# between the tape stage and the ddmin stage: delete k consecutive lines after the first (3a) or k consecutive tokens
# of one such line (3b), each with the first line unchanged or with one of its integer tokens decremented by k
# (never below 0); k halves from the largest power of two to 1. info.json gains stage_sizes (tokens, bytes at
# every stage boundary) and shrinker "s2".

TOKEN = re.compile(r"-?\d+|\S")
TAPE_BUDGET, BUDGET_EXIT = 1_000_000, 85
CHECKER_VERDICT = {0: "ok", 1: "WA", 2: "PE", 3: "ref_fail", 4: "dirt", 8: "EOF"}


class Budget(Exception):
    pass


def ntokens(text):
    return len(TOKEN.findall(text))


def size_key(text):
    return (ntokens(text), len(text.encode()))


class Judge:
    """Verdict of an input from fresh processes: invalid / ref_crash / ref_tle / RE / TLE / WA / ok / PE / dirt /
    EOF / ref_fail / checker_error. Only "WA" preserves a bug."""

    def __init__(self, problem, tmp, fast=None):
        p = problems.get(problem)
        bins = problems.plain_bins(p, "sol_bug")
        self.verifier = str(problems.ROOT / "build" / problem / "verifier")
        self.ref, self.fast = str(bins["brute"]), str(fast or bins["sol_bug"])
        self.checker = str(bins["checker"]) if p["checker_kind"] == "custom" else None
        self.inp, self.out, self.ans = (tmp / "in", tmp / "out", tmp / "ans")

    def verdict(self, text):
        self.inp.write_bytes(text.encode())
        with open(self.inp, "rb") as f:
            if subprocess.run([self.verifier], stdin=f, capture_output=True).returncode != 0:
                return "invalid"
        rc = problems._run([self.ref], self.inp, self.ans, None, "")
        if rc != 0:
            return "ref_tle" if rc is None else "ref_crash"
        rc = problems._run([self.fast], self.inp, self.out, None, "")
        if rc != 0:
            return "TLE" if rc is None else "RE"
        if self.checker:
            try:
                rc = subprocess.run([self.checker, str(self.inp), str(self.out), str(self.ans)], capture_output=True,
                                    timeout=problems.TIMEOUT).returncode
            except subprocess.TimeoutExpired:
                return "checker_error"
            return CHECKER_VERDICT.get(rc, "checker_error")
        a, b = self.out.read_bytes().split(), self.ans.read_bytes().split()
        return "PE" if len(a) != len(b) else "WA" if a != b else "ok"


class TapeGen:
    """build/tape/<problem>/<gen|gen_alt>: (exit code, output text, consumed words, draw log [(index, upper)])."""

    def __init__(self, problem, variant, seed, size, tmp):
        self.exe = str(problems.ROOT / "build" / "tape" / problem / ("gen_alt" if variant else "gen"))
        self.args, self.tmp = [str(seed), str(size)], tmp

    def run(self, words, fallback_zero):
        t_in, t_out, t_log = self.tmp / "tape_in", self.tmp / "tape_out", self.tmp / "tape_log"
        t_in.write_bytes(struct.pack(f"<{len(words)}Q", *words))
        for f in (t_out, t_log):
            f.unlink(missing_ok=True)
        env = dict(os.environ, CF_TAPE_IN=str(t_in), CF_TAPE_OUT=str(t_out), CF_TAPE_LOG=str(t_log),
                   CF_TAPE_FALLBACK_ZERO="1" if fallback_zero else "0", CF_TAPE_BUDGET=str(TAPE_BUDGET))
        try:
            r = subprocess.run([self.exe, *self.args], env=env, capture_output=True, timeout=problems.TIMEOUT)
        except subprocess.TimeoutExpired:
            return None, "", [], []
        if r.returncode != 0:
            return r.returncode, "", [], []
        out, log = t_out.read_bytes(), t_log.read_bytes()
        words = list(struct.unpack(f"<{len(out) // 8}Q", out))
        flat = struct.unpack(f"<{len(log) // 8}Q", log)
        return 0, r.stdout.decode(), words, list(zip(flat[0::2], flat[1::2]))


def read_bug(bug_dir):
    recipe = dict(l.split(None, 1) for l in (bug_dir / "recipe.txt").read_text().splitlines() if l.strip())
    tape = bug_dir / "tape.bin"
    words = list(struct.unpack(f"<{tape.stat().st_size // 8}Q", tape.read_bytes())) if tape.exists() else []
    return int(recipe["variant"]), int(recipe["size"]), int(recipe["seed"]), words


def capture(problem, bug_dir, tmp):
    """Stage 0: (ok, words, log, text); ok = the regenerated input hashes to input.txt."""
    variant, size, seed, words = read_bug(bug_dir)
    rc, text, out, log = TapeGen(problem, variant, seed, size, tmp).run(words, False)
    want = hashlib.sha256((bug_dir / "input.txt").read_bytes()).hexdigest()
    return rc == 0 and hashlib.sha256(text.encode()).hexdigest() == want, out, log, text


def smaller(a, b):  # strict progress order on tapes (shorter, then lexicographically smaller): no cycles
    return (len(a), a) < (len(b), b)


def mask_of(upper):  # as in random.h next(upper)
    return upper if not (upper & (upper + 1)) else (1 << upper.bit_length()) - 1


def s2_pieces(line):  # (whitespace before, token) for every token of a line
    parts = [(m.start(), m.group()) for m in TOKEN.finditer(line)]
    return [(line[(parts[i - 1][0] + len(parts[i - 1][1])) if i else 0:pos], tok) for i, (pos, tok) in enumerate(parts)]


def s2_join(pieces):
    return "".join(sep + tok for sep, tok in pieces).lstrip()


def s2_heads(first, k):
    """The first line unchanged, then with each of its integer tokens decremented by k (not below 0 if >= 0)."""
    head, out = s2_pieces(first), [first]
    for i, (_, tok) in enumerate(head):
        if re.fullmatch(r"-?\d+", tok) and not (int(tok) >= 0 and int(tok) - k < 0):
            out.append(s2_join([(sep, str(int(t) - k) if j == i else t) for j, (sep, t) in enumerate(head)]))
    return out


class Shrinker:
    def __init__(self, problem, bug_dir, tmp, max_evals, wall, judge=None, s2=False):
        self.s2, self.sizes = s2, {}
        self.judge = judge or Judge(problem, tmp)
        variant, size, seed, _ = read_bug(bug_dir)
        self.gen = TapeGen(problem, variant, seed, size, tmp)
        self.max_evals, self.wall, self.t0 = max_evals, wall, time.time()
        self.evals, self.text_cache, self.tape_cache, self.best, self.stop = 0, {}, {}, None, "done"
        self.stage_evals, self.accepted = {}, {}

    def check(self):  # called for every candidate, memoised or not, so no loop can outrun the budget
        if self.evals >= self.max_evals:
            raise Budget("evaluation cap")
        if time.time() - self.t0 > self.wall:
            raise Budget("wall")

    def spend(self, stage):
        self.check()
        self.evals += 1
        self.stage_evals[stage] = self.stage_evals.get(stage, 0) + 1

    def keep(self, text):  # smallest bug-preserving input seen
        if self.best is None or size_key(text) < size_key(self.best):
            self.best = text

    def text_ok(self, text, stage):
        self.check()
        if text not in self.text_cache:
            self.spend(stage)
            self.text_cache[text] = self.judge.verdict(text) == "WA"
        if self.text_cache[text]:
            self.keep(text)
        return self.text_cache[text]

    def tape_ok(self, words, stage):
        """-> (ok, consumed words without trailing zeros, draw log) of a tape candidate (fallback_zero on: trailing
        zero words are redundant, so tapes are kept normalised)."""
        self.check()
        key = struct.pack(f"<{len(words)}Q", *words)
        if key not in self.tape_cache:
            self.spend(stage)
            rc, text, out, log = self.gen.run(words, True)
            ok = False
            if rc == 0:  # a budget exit (85), crash or timeout rejects the candidate
                if text not in self.text_cache:
                    self.text_cache[text] = self.judge.verdict(text) == "WA"
                ok = self.text_cache[text]
                if ok:
                    self.keep(text)
            while out and out[-1] == 0:
                out = out[:-1]
            self.tape_cache[key] = (ok, out, log)
        return self.tape_cache[key]

    def accept(self, stage):
        self.accepted[stage] = self.accepted.get(stage, 0) + 1

    def tape_stage(self, words, log):
        while words and words[-1] == 0:  # normalised like every candidate
            words = words[:-1]
        changed = True
        while changed:
            changed = False
            lo, hi = 0, len(words)  # 1a truncate: shortest prefix that still preserves the bug
            while lo < hi:
                mid = (lo + hi) // 2
                if self.tape_ok(words[:mid], "1a")[0]:
                    hi = mid
                else:
                    lo = mid + 1
            if hi < len(words):
                ok, out, lg = self.tape_ok(words[:hi], "1a")
                if ok and smaller(out, words):
                    words, log, changed = out, lg, True
                    self.accept("1a")
            for k in (8, 4, 2, 1):  # 1b delete spans, left to right
                i = 0
                while i < len(words):
                    ok, out, lg = self.tape_ok(words[:i] + words[i + k:], "1b")
                    if ok and smaller(out, words):  # progress only: deleting re-padded zeros changes nothing
                        words, log, changed = out, lg, True
                        self.accept("1b")
                    else:
                        i += k
            d = 0  # 1c zero each draw, left to right
            while d < len(log):
                idx, upper = log[d]
                if idx < len(words) and words[idx] & mask_of(upper):
                    cand = list(words)
                    cand[idx] = 0
                    ok, out, lg = self.tape_ok(cand, "1c")
                    if ok and smaller(out, words):
                        words, log, changed = out, lg, True
                        self.accept("1c")
                d += 1
            d = 0  # 1d reduce each remaining draw value by binary search toward 0
            while d < len(log):
                idx, upper = log[d]
                v = words[idx] & mask_of(upper) if idx < len(words) else 0
                lo, hi = 0, v
                while lo < hi:
                    mid = (lo + hi) // 2
                    cand = list(words)
                    cand[idx] = mid
                    if self.tape_ok(cand, "1d")[0]:
                        hi = mid
                    else:
                        lo = mid + 1
                if hi < v:
                    cand = list(words)
                    cand[idx] = hi
                    ok, out, lg = self.tape_ok(cand, "1d")
                    if ok and smaller(out, words):
                        words, log, changed = out, lg, True
                        self.accept("1d")
                d += 1
        return words

    def ddmin(self, items, test, stage):
        """Zeller's ddmin over complements: the smallest sub-list (in this order) with test() true."""
        n = 2
        while len(items) >= 2:
            chunk = math.ceil(len(items) / n)
            parts = [items[i:i + chunk] for i in range(0, len(items), chunk)]
            for i in range(len(parts)):
                cand = [x for j, part in enumerate(parts) if j != i for x in part]
                if test(cand):
                    items, n = cand, max(n - 1, 2)
                    self.accept(stage)
                    break
            else:
                if n >= len(items):
                    break
                n = min(2 * n, len(items))
        return items

    def text_stage(self, text):
        end = "\n" if text.endswith("\n") else ""
        lines = text[:len(text) - len(end)].split("\n")
        join = lambda ls: "\n".join(ls) + end
        lines = self.ddmin(lines, lambda ls: self.text_ok(join(ls), "2a"), "2a")
        for j in range(len(lines)):  # token-level within each line; a token keeps the whitespace before it
            parts = [(m.start(), m.group()) for m in TOKEN.finditer(lines[j])]
            pieces = [(lines[j][(parts[i - 1][0] + len(parts[i - 1][1])) if i else 0:pos], tok) for i, (pos, tok) in enumerate(parts)]
            line = lambda ps: "".join(sep + tok for sep, tok in ps).lstrip()
            kept = self.ddmin(pieces, lambda ps: self.text_ok(join(lines[:j] + [line(ps)] + lines[j + 1:]), "2b"), "2b")
            lines[j] = line(kept)
        return join(lines)

    def mark(self, name):  # S2: input size at a stage boundary
        self.sizes[name] = dict(tokens=ntokens(self.best), bytes=len(self.best.encode()))

    def count_stage(self, text):
        """S2 stage 3: count-aware deletions (see the header comment). Every accepted candidate has fewer tokens."""
        end = "\n" if text.endswith("\n") else ""
        lines = text[:len(text) - len(end)].split("\n")
        join = lambda ls: "\n".join(ls) + end

        def first_ok(cands, stage):  # first bug-preserving candidate (list of lines) that is strictly smaller
            for c in cands:
                if size_key(join(c)) < size_key(join(lines)) and self.text_ok(join(c), stage):
                    return c
            return None

        changed = True
        while changed:
            changed = False
            nb = len(lines) - 1  # 3a: line chunks; k starts at the largest power of two <= the number of body lines
            k = 1 << (nb.bit_length() - 1) if nb else 0
            while k >= 1:
                i = 1
                while i < len(lines):
                    body = lines[1:i] + lines[i + k:]
                    c = first_ok([[h] + body for h in s2_heads(lines[0], k)], "3a")
                    if c:
                        lines, changed = c, True
                        self.accept("3a")
                    else:
                        i += k
                k //= 2
            for j in range(1, len(lines)):  # 3b: token chunks within each line after the first
                ps = s2_pieces(lines[j])
                k = 1 << (len(ps).bit_length() - 1) if ps else 0
                while k >= 1:
                    i = 0
                    while i < len(ps):
                        rest = s2_join(ps[:i] + ps[i + k:])
                        c = first_ok([[h] + lines[1:j] + [rest] + lines[j + 1:] for h in s2_heads(lines[0], k)], "3b")
                        if c:
                            lines, changed = c, True
                            ps = s2_pieces(lines[j])
                            self.accept("3b")
                        else:
                            i += k
                    k //= 2
        return join(lines)

    def run(self, words, log, text):
        self.keep(text)
        try:
            words = self.tape_stage(words, log)
            if self.s2:
                self.mark("after_tape")
                self.count_stage(self.best)
                self.mark("after_count")
            self.text_stage(self.best)
            if self.s2:
                self.mark("after_ddmin")
        except Budget as b:
            self.stop = str(b)
            if self.s2:
                self.mark("at_stop")
        return self.best


def shrink_bug(problem, bug_dir, out_dir, max_evals=2000, wall=60.0, s1=False):
    """Shrink one bug into out_dir (input.txt, info.json) -> info dict. s1: the S1 shrinker (no stage 3, S1's info)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(f"/dev/shm/cf_shrink_{os.getpid()}")
    tmp.mkdir(exist_ok=True)
    t0, original = time.time(), (bug_dir / "input.txt").read_text()
    try:
        ok, words, log, _ = capture(problem, bug_dir, tmp)
        judge = Judge(problem, tmp)
        info = dict(problem=problem, bug_dir=str(bug_dir), capture_ok=ok, original_verdict=judge.verdict(original),
                    before=dict(tokens=ntokens(original), bytes=len(original.encode())))
        best, s = original, None
        if ok and info["original_verdict"] == "WA":
            s = Shrinker(problem, bug_dir, tmp, max_evals, wall, judge, s2=not s1)
            best = s.run(words, log, original)
        final = judge.verdict(best)
        info.update(after=dict(tokens=ntokens(best), bytes=len(best.encode())), final_verdict=final,
                    success=final == "WA", evals=s.evals if s else 0, stop=s.stop if s else "not shrunk",
                    stage_evals=s.stage_evals if s else {}, accepted=s.accepted if s else {},
                    wall_s=round(time.time() - t0, 3))
        if not s1:
            info.update(shrinker="s2", stage_sizes=dict(start=info["before"], **(s.sizes if s else {})))
        (out_dir / "input.txt").write_text(best)
        (out_dir / "info.json").write_text(json.dumps(info, indent=1) + "\n")
        return info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def new_main():
    ap = argparse.ArgumentParser(description="v2 shrinker (default); --old runs the generator-space shrinker")
    ap.add_argument("problem")
    ap.add_argument("bug_dir", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="output directory (never the bug directory)")
    ap.add_argument("--max-evals", type=int, default=2000)
    ap.add_argument("--wall", type=float, default=60.0)
    ap.add_argument("--s1", action="store_true", help="the S1 shrinker (no count-aware stage), unchanged")
    a = ap.parse_args()
    if a.out.resolve() == a.bug_dir.resolve():
        raise SystemExit("--out must not be the bug directory")
    info = shrink_bug(a.problem, a.bug_dir, a.out, a.max_evals, a.wall, a.s1)
    print(json.dumps({k: info[k] for k in ("capture_ok", "original_verdict", "before", "after", "success", "evals", "stop", "wall_s")}))
    return 0 if info["success"] else 1


if __name__ == "__main__":
    if "--old" in sys.argv:  # the old generator-space shrinker, unchanged
        sys.argv.remove("--old")
        raise SystemExit(main())
    raise SystemExit(new_main())
