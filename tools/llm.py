#!/usr/bin/env python3
"""Local LLM layer (Ollama over HTTP, outside the timed region). Two subcommands:
  explain --model M : for every gallery bug, show the model sol_bug.cpp (line-numbered, changed comments
                      blanked), the shrunk input and both outputs; ask for {line, category, explanation, fix};
                      score against Dataset/bugs.json (line within +-3, exact category) -> results/llm/explain_<M>.json
  gen --model M     : for every hard-tier problem, ask for a generator from verifier.cpp + params.h + random_api.txt;
                      compile (one repair round), measure verifier acceptance and bug detection vs the dataset
                      generator on seeds 1..100 x sizes 5, 20, max -> results/llm/gen_<M>.json
Server: $OLLAMA_URL (default http://localhost:11434). Prompts are saved to results/llm/prompts/<M>/.
"""
import argparse, difflib, json, os, re, statistics, subprocess, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import problems

ROOT, OUT = problems.ROOT, problems.ROOT / "results" / "llm"
URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
CATEGORIES = ["off-by-one", "boundary", "init", "edge-case", "narrowing", "modulo", "tie-break"]
MAX_TOKENS, CHARS_PER_TOKEN = 7000, 3.5
SEEDS, SIZES = range(1, 101), (5, 20, "max")


def chat(model, prompt, schema=None):
    """One /api/chat call -> (content, stats). stats: latency_s, prompt_tokens, response_tokens."""
    body = {"model": model, "stream": False, "messages": [{"role": "user", "content": prompt}],
            "options": {"num_ctx": 8192, "temperature": 0.2, "seed": 1}}
    if schema:
        body["format"] = schema
    if model.startswith("qwen3"):
        body["think"] = False
    t = time.time()
    req = urllib.request.Request(f"{URL}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=900).read())
    return r["message"]["content"], dict(latency_s=round(time.time() - t, 2), prompt_tokens=r.get("prompt_eval_count"),
                                         response_tokens=r.get("eval_count"))


def slug(model):
    return re.sub(r"[^A-Za-z0-9.]+", "_", model)


def save_prompt(model, name, text):
    d = OUT / "prompts" / slug(model)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.txt").write_text(text)


def comment_of(line):
    m = re.search(r"//.*|/\*.*?\*/", line)
    return m.group(0) if m else None


def blank_new_comments(sol, bug):
    """Bug-version lines whose comments do not appear in the replaced sol.cpp lines lose those comments
    (in the prompt copy only; line count unchanged). Returns (lines, number of comments blanked)."""
    a, b = sol.splitlines(), bug.splitlines()
    out, blanked = list(b), 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            old = "\n".join(a[i1:i2])
            for j in range(j1, j2):
                c = comment_of(b[j])
                if c and c not in old:
                    out[j] = b[j].replace(c, "").rstrip()
                    blanked += 1
    return out, blanked


def first_diff(ref, fast):
    r, f = ref.split(), fast.split()
    i = next((k for k in range(max(len(r), len(f))) if r[k:k + 1] != f[k:k + 1]), None)
    if i is None:
        return "the outputs have the same tokens (the checker still rejects the buggy output)"
    get = lambda t: t[i] if i < len(t) else "<missing>"
    return f"first differing token is token #{i + 1} (1-based, whitespace-separated): expected {get(r)!r}, got {get(f)!r}"


EXPLAIN_SCHEMA = {"type": "object", "required": ["line", "category", "explanation", "fix"], "properties": {
    "line": {"type": "integer"}, "category": {"type": "string", "enum": CATEGORIES},
    "explanation": {"type": "string"}, "fix": {"type": "string"}}}


def explain_one(code_text, input_text, ref_out, fast_out, model, name=None):
    """Ask the model to locate the bug in code_text (plain source, numbered here). Returns a dict:
    status ok|too_long|bad_json, prompt, n_lines, prompt_tokens_est, and for ok/bad_json the chat stats plus
    line, category, explanation, fix (bad_json: raw)."""
    lines = code_text.splitlines()
    code = "\n".join(f"{i}| {l}" for i, l in enumerate(lines, 1))
    what = f'for the competitive-programming problem "{name}"' if name else "for a competitive-programming problem"
    prompt = (f"The C++ solution below {what} contains exactly one bug.\n"
              f"It produces a wrong answer on the input shown. Find the bug.\n\n"
              f"Solution (each line is prefixed with its line number and '| '):\n{code}\n\n"
              f"Input:\n{input_text}\nExpected output (correct reference):\n{ref_out}\nActual output (this solution):\n{fast_out}\n"
              f"Where they differ: {first_diff(ref_out, fast_out)}.\n\n"
              f"Answer in JSON: line = the line number of the bug, category = one of {CATEGORIES}, "
              f"explanation = 2-4 sentences, fix = one line of corrected code.")
    row = dict(prompt=prompt, n_lines=len(lines), prompt_tokens_est=round(len(prompt) / CHARS_PER_TOKEN))
    if len(prompt) / CHARS_PER_TOKEN > MAX_TOKENS:
        return dict(row, status="too_long")
    content, stats = chat(model, prompt, EXPLAIN_SCHEMA)
    try:
        a = json.loads(content)
        return dict(row, status="ok", **stats, line=a["line"], category=a["category"],
                    explanation=a["explanation"], fix=a["fix"])
    except (ValueError, KeyError):
        return dict(row, status="bad_json", **stats, raw=content[:2000])


def explain(model):
    bugs = {b["problem"]: b for b in json.loads((problems.DATASET / "bugs.json").read_text())}
    gallery = json.loads((ROOT / "results" / "bugs" / "gallery.json").read_text())
    rows = []
    for g in gallery:
        name = g["problem"]  # only the name is used from the gallery row
        p = problems.get(name)
        lines, blanked = blank_new_comments((p["dir"] / "sol.cpp").read_text(), (p["dir"] / "sol_bug.cpp").read_text())
        shrunk = ROOT / "results" / "bugs" / name / "shrunk"
        inp, ref, fast = ((shrunk / f).read_text() for f in ("input.txt", "ref_out.txt", "fast_out.txt"))
        true = bugs[name]
        r = explain_one("\n".join(lines), inp, ref, fast, model, name)
        save_prompt(model, f"explain_{name}", r.pop("prompt"))
        row = dict(problem=name, true_line=true["line"], true_category=true["category"], comments_blanked=blanked, **r)
        if r["status"] == "ok":
            row.update(line_ok=abs(r["line"] - true["line"]) <= 3, category_ok=r["category"] == true["category"])
        rows.append(row)
        r = row
        print(f"{name:42} blanked={blanked} {r['status']:8} line {r.get('line', '-')!s:>4} (true {true['line']:>4}) "
              f"{'✓' if r.get('line_ok') else '✗'}  cat {r.get('category', '-'):10} {'✓' if r.get('category_ok') else '✗'}  "
              f"{r.get('latency_s', 0):5.1f}s", flush=True)
    ok = [r for r in rows if r["status"] == "ok"]
    summary = dict(model=model, n=len(rows), n_explained=len(ok), n_too_long=sum(r["status"] == "too_long" for r in rows),
                   n_bad_json=sum(r["status"] == "bad_json" for r in rows),
                   line_acc=sum(r["line_ok"] for r in ok) / len(ok) if ok else None,
                   category_acc=sum(r["category_ok"] for r in ok) / len(ok) if ok else None,
                   chance_line_acc=statistics.mean(min(1, 7 / r["n_lines"]) for r in ok) if ok else None,
                   median_latency_s=statistics.median(r["latency_s"] for r in ok) if ok else None)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"explain_{slug(model)}.json").write_text(json.dumps(dict(summary=summary, problems=rows), indent=1) + "\n")
    print(json.dumps(summary, indent=1))


def cpp_block(text):
    m = re.search(r"```(?:cpp|c\+\+)?\s*\n(.*?)```", text, re.S)
    return m.group(1) if m else None


def compile_gen(p, src, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    src_path = out.with_suffix(".cpp")
    src_path.write_text(src or "")
    r = subprocess.run(["g++", "-O2", "-std=c++17", "-w", "-I", str(problems.DATASET / "common"), "-I", str(p["dir"]),
                        "-I", str(p["dir"] / "gen"), "-o", str(out), str(src_path)], capture_output=True, text=True)
    return r.returncode == 0 and src is not None, r.stderr[-3000:] if src else "no ```cpp block in the answer"


def evaluate_gen(p, gen_path, max_size):
    """Verifier acceptance and bug rate of the LLM generator, plus the dataset generator's bug rate."""
    verifier = ROOT / "build" / p["name"] / "verifier"
    jobs = [(seed, max_size if s == "max" else s) for s in SIZES for seed in SEEDS]

    def one(job):
        seed, size = job
        llm_outcome, text = problems.run_test(p, 0, size, seed, "bug", gen=gen_path)
        accepted = llm_outcome != "gen_skip" and subprocess.run([str(verifier)], input=text.encode(),
                                                                  capture_output=True).returncode == 0
        ds_outcome, _ = problems.run_test(p, 0, size, seed, "bug")
        return accepted, llm_outcome, ds_outcome

    with ThreadPoolExecutor(os.cpu_count()) as ex:
        res = list(ex.map(one, jobs))
    acc = [o for a, o, _ in res if a]
    ds_valid = [d for _, _, d in res if d in ("ok", *problems.BUGS)]
    return dict(tests=len(res), acceptance=len(acc) / len(res),
                llm_bug_rate=sum(o in problems.BUGS for o in acc) / len(acc) if acc else None,
                llm_invalid_after_accept=sum(o == "invalid" for o in acc),
                dataset_bug_rate=sum(d in problems.BUGS for d in ds_valid) / len(ds_valid) if ds_valid else None)


def gen(model):
    bugs = json.loads((problems.DATASET / "bugs.json").read_text())
    fuzz = json.loads((ROOT / "fuzz_config.json").read_text())
    api = (ROOT / "tools" / "random_api.txt").read_text()
    rows = []
    for name in [b["problem"] for b in bugs if b["tier"] == "hard"]:
        p = problems.get(name)
        max_size = fuzz[name]["max_size"]
        prompt = (f"Write a random test generator in C++17 for the competitive-programming problem \"{name}\".\n"
                  f"The input format and constraints are defined by this testlib verifier (verifier.cpp):\n"
                  f"```cpp\n{(p['dir'] / 'verifier.cpp').read_text()}```\n"
                  f"Constants (params.h, include it with #include \"params.h\"):\n```cpp\n{(p['dir'] / 'params.h').read_text()}```\n"
                  f"Random number API (#include \"random.h\"):\n{api}\n"
                  f"Requirements: usage `./gen <seed> <size>`; seed it with Random gen(seed); print exactly one valid input "
                  f"to stdout; `size` (1..{max_size}) bounds the main dimensions (n, q, string lengths, ...); every value "
                  f"must satisfy the verifier; use only the C++ standard library and random.h (no testlib). "
                  f"Answer with one ```cpp code block containing the whole program.")
        save_prompt(model, f"gen_{name}", prompt)
        out = ROOT / "build" / "llm" / slug(model) / name / "gen"
        content, stats = chat(model, prompt)
        ok, err = compile_gen(p, cpp_block(content), out)
        latency, attempts = stats["latency_s"], 1
        if not ok:
            repair = (f"{prompt}\n\nYour previous answer:\n{content}\n\nIt failed to compile with these errors:\n{err}\n"
                      f"Fix it. Answer with one ```cpp code block containing the whole program.")
            save_prompt(model, f"gen_{name}_repair", repair)
            content, stats = chat(model, repair)
            ok, err = compile_gen(p, cpp_block(content), out)
            latency, attempts = latency + stats["latency_s"], 2
        row = dict(problem=name, attempts=attempts, compiled=ok, latency_s=round(latency, 2),
                   compile_error=None if ok else err[:500])
        row.update(evaluate_gen(p, out, max_size) if ok else {})
        rows.append(row)
        pct = lambda x: "-" if x is None else f"{100 * x:5.1f}%"
        print(f"{name:34} attempts={attempts} compiled={ok!s:5} acceptance={pct(row.get('acceptance'))} "
              f"bug rate LLM={pct(row.get('llm_bug_rate'))} dataset={pct(row.get('dataset_bug_rate'))}  {latency:5.1f}s", flush=True)
    comp = [r for r in rows if r["compiled"]]
    summary = dict(model=model, n=len(rows), compiled_first_try=sum(r["compiled"] and r["attempts"] == 1 for r in rows),
                   compiled_after_repair=sum(r["compiled"] and r["attempts"] == 2 for r in rows),
                   mean_acceptance=statistics.mean(r["acceptance"] for r in comp) if comp else None,
                   mean_llm_bug_rate=statistics.mean(r["llm_bug_rate"] for r in comp if r["llm_bug_rate"] is not None) if comp else None,
                   mean_dataset_bug_rate=statistics.mean(r["dataset_bug_rate"] for r in comp) if comp else None)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"gen_{slug(model)}.json").write_text(json.dumps(dict(summary=summary, problems=rows), indent=1) + "\n")
    print(json.dumps(summary, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["explain", "gen"])
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    a = ap.parse_args()
    (explain if a.command == "explain" else gen)(a.model)


if __name__ == "__main__":
    sys.exit(main())
