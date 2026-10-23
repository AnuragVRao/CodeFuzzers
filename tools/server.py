#!/usr/bin/env python3
"""Analysis server: upload gen/ref/sol (+checker), queue, run tools/analyze.py, stream progress.
Usage: python3 tools/server.py   (binds 127.0.0.1:8000 only; CF_PORT / CF_JOBS_DIR override port and job directory, used by tests)
Jobs live in results/jobs/<id>/ (gen.cpp ref.cpp sol.cpp [checker.cpp] config.json status.json progress.jsonl
report.json analyze.log ...); uploads are saved under fixed names, client file names are never used.
One worker thread runs jobs FIFO. Each job is a process group with resource limits; it is killed on cancel,
after budget_s + 120 s, and always swept after it ends. Jobs found queued/running at startup become "interrupted".
"""
import asyncio, collections, contextlib, json, os, re, resource, secrets, shutil, signal, subprocess, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from starlette.datastructures import UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

ROOT = Path(__file__).resolve().parent.parent
JOBS, EXAMPLES = Path(os.environ.get("CF_JOBS_DIR", ROOT / "results" / "jobs")), ROOT / "examples"
PORT = int(os.environ.get("CF_PORT", 8000))
WALL_LIMIT_OVERRIDE_S = os.environ.get("CF_WALL_LIMIT_OVERRIDE_S")  # TEST-ONLY (tools/e2e_test.sh): replaces budget_s + 120
MAX_BYTES, BUDGETS = 1 << 20, (60, 180, 600)
TERMINAL = ("done", "failed", "cancelled", "timeout", "interrupted")
ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}$")
LOCK, WAKE = threading.Lock(), threading.Condition()
queue, current, cancel_flag = collections.deque(), None, threading.Event()


# ---------------------------------------------------------------- job state
def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def update(jid, **fields):
    """Merge fields into status.json (atomic replace) and return the new status."""
    with LOCK:
        f = JOBS / jid / "status.json"
        st = {**read_json(f, {}), **fields}
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=1) + "\n")
        os.replace(tmp, f)
        return st


def job_dir(jid):
    if not ID_RE.match(jid) or not (JOBS / jid / "status.json").exists():
        raise HTTPException(404, "no such job")
    return JOBS / jid


def new_job(files, config):
    """Create results/jobs/<id>/ with the given {fixed name: text} files and config; queue it."""
    jid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    d = JOBS / jid
    d.mkdir(parents=True)
    for name, text in files.items():
        (d / name).write_text(text)
    (d / "config.json").write_text(json.dumps(config, indent=1) + "\n")
    with WAKE:
        position = len(queue) + (current is not None)
        st0 = dict(id=jid, created=datetime.now(timezone.utc).isoformat(timespec="seconds"), state="queued",
                          budget_s=config["budget_s"], outcome_summary=None, error=None)
        (d / "status.json").write_text(json.dumps(st0, indent=1) + "\n")
        queue.append(jid)
        WAKE.notify()
    return dict(id=jid, state="queued", queue_position=position)


def outcome_of(d):
    """(outcome_summary, error) of a finished analyze.py run, from report.json / progress.jsonl."""
    rep = read_json(d / "report.json", {})
    if rep.get("status") == "completed":
        if rep.get("bug"):
            return f"{rep['bug']['kind']} found after {rep['hunt']['first_bug']['tests_before'] + 1} tests", None
        return f"clean: <{100 * rep['clean_bound']['upper95']:.2g}%", None
    events = []
    for line in (d / "progress.jsonl").read_text().splitlines() if (d / "progress.jsonl").exists() else []:
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    fails = [e for e in events if e["status"] == "fail" and e["stage"] != "pipeline"] or [e for e in events if e["status"] == "fail"]
    if fails:
        return f"failed: {fails[-1]['stage']}", fails[-1]["message"]
    return "failed", "analysis exited without a report (see analyze.log)"


# ---------------------------------------------------------------- execution
def set_limits():
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 << 20, 256 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NPROC, (4096, 4096))


def killpg(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def stop_group(proc):
    killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(3)
    except subprocess.TimeoutExpired:
        killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def run_job(jid):
    d = JOBS / jid
    budget = read_json(d / "status.json")["budget_s"]
    update(jid, state="running", started=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with open(d / "analyze.log", "wb") as log:
        proc = subprocess.Popen([sys.executable, str(ROOT / "tools" / "analyze.py"), str(d)], stdout=log, stderr=subprocess.STDOUT,
                                cwd=ROOT, start_new_session=True, preexec_fn=set_limits)
        update(jid, pid=proc.pid)
        deadline, state = time.time() + (float(WALL_LIMIT_OVERRIDE_S) if WALL_LIMIT_OVERRIDE_S else budget + 120), None
        while proc.poll() is None:
            if cancel_flag.is_set():
                state = "cancelled"
            elif time.time() > deadline:
                state = "timeout"
            if state:
                stop_group(proc)
                break
            time.sleep(0.2)
    killpg(proc.pid, signal.SIGKILL)  # leftovers of any end state
    if state:
        update(jid, state=state, outcome_summary=state, error=None, finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    else:
        summary, error = outcome_of(d)
        update(jid, state="done" if proc.returncode == 0 else "failed", outcome_summary=summary, error=error if proc.returncode else None,
               finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if proc.returncode not in (0, 1):
            update(jid, error=f"analyze.py exited with code {proc.returncode} (see analyze.log)")


def worker():
    global current
    while True:
        with WAKE:
            while not queue:
                WAKE.wait()
            jid = queue.popleft()
            current = jid
            cancel_flag.clear()
        try:
            run_job(jid)
        except Exception as e:  # never let the worker thread die
            update(jid, state="failed", error=f"server error: {e!r}")
        current = None


def reap_old_jobs():
    """Startup: queued/running jobs from a previous server become interrupted; their process group is killed."""
    for f in JOBS.glob("*/status.json"):
        st = read_json(f, {})
        if st.get("state") in ("queued", "running"):
            pid = st.get("pid")
            if pid and "analyze.py" in (Path(f"/proc/{pid}/cmdline").read_text().replace("\0", " ") if Path(f"/proc/{pid}").exists() else ""):
                killpg(pid, signal.SIGKILL)
            update(f.parent.name, state="interrupted", outcome_summary="interrupted", error="server restarted while the job was queued or running")


# ---------------------------------------------------------------- API
@contextlib.asynccontextmanager
async def lifespan(app):
    JOBS.mkdir(parents=True, exist_ok=True)
    reap_old_jobs()
    threading.Thread(target=worker, daemon=True).start()
    yield
    if current:  # server stopping: do not leave the running job's processes behind
        cancel_flag.set()
        st = read_json(JOBS / current / "status.json", {})
        if st.get("pid"):
            killpg(st["pid"], signal.SIGKILL)
        update(current, state="interrupted", outcome_summary="interrupted", error="server stopped")


app = FastAPI(title="CodeFuzzers analysis server", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


def check_template(t):
    toks = t.split()
    if "{seed}" not in toks:
        raise HTTPException(400, "gen_template must contain a whole {seed} token")
    for tok in toks:
        if tok not in ("{seed}", "{size}") and ("{seed}" in tok or "{size}" in tok):
            raise HTTPException(400, f"gen_template token {tok!r} must be exactly {{seed}} or {{size}}, not merely contain it")


async def read_source(f, name):
    data = await f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(400, f"{name} is larger than 1 MB")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, f"{name} is not valid UTF-8 text")


@app.post("/api/jobs")
async def create_job(request: Request):
    form = await request.form()
    texts = {}
    for key in ("gen", "ref", "sol", "checker"):
        f = form.get(key)
        if isinstance(f, UploadFile) and f.filename:
            texts[key] = await read_source(f, key)
        elif key != "checker":
            raise HTTPException(400, f"missing file: {key}")
    mode = form.get("checker_mode", "exact")
    if mode not in ("exact", "custom"):
        raise HTTPException(400, "checker_mode must be exact or custom")
    if mode == "custom" and "checker" not in texts:
        raise HTTPException(400, "checker_mode custom needs a checker file")
    try:
        budget = int(form.get("budget_s", 180))
    except ValueError:
        budget = None
    if budget not in BUDGETS:
        raise HTTPException(400, f"budget_s must be one of {list(BUDGETS)}")
    template = str(form.get("gen_template", "{seed} {size}"))
    check_template(template)
    files = {f"{k}.cpp": v for k, v in texts.items() if k != "checker" or mode == "custom"}
    return new_job(files, dict(gen_template=template, checker=mode, budget_s=budget, workers=20, llm_model="qwen3:8b"))


@app.get("/api/jobs")
def list_jobs():
    jobs = [read_json(f, {}) for f in JOBS.glob("*/status.json")]
    return sorted(jobs, key=lambda s: s.get("id", ""), reverse=True)


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    d = job_dir(jid)
    return {**read_json(d / "status.json"), "report": read_json(d / "report.json")}


FILES = {"gen.cpp": "gen.cpp", "ref.cpp": "ref.cpp", "sol.cpp": "sol.cpp", "checker.cpp": "checker.cpp",
         "shrunk_input.txt": "shrunk/input.txt", "shrunk_ref_out.txt": "shrunk/ref_out.txt", "shrunk_fast_out.txt": "shrunk/fast_out.txt"}


@app.get("/api/jobs/{jid}/files/{name}", response_class=PlainTextResponse)
def get_file(jid: str, name: str):
    d = job_dir(jid)
    if name not in FILES or not (d / FILES[name]).is_file():
        raise HTTPException(404, "no such file")
    return (d / FILES[name]).read_text(errors="replace")


@app.get("/api/jobs/{jid}/events")
async def events(jid: str, request: Request):
    d = job_dir(jid)
    start = int(request.headers.get("last-event-id", "-1")) + 1 if request.headers.get("last-event-id", "-1").lstrip("-").isdigit() else 0

    async def stream():
        n = start
        while True:
            state = read_json(d / "status.json", {}).get("state")  # read before the log, so no line is missed
            lines = (d / "progress.jsonl").read_text().splitlines() if (d / "progress.jsonl").exists() else []
            for i in range(n, len(lines)):
                yield f"id: {i}\ndata: {lines[i]}\n\n"
            n = max(n, len(lines))
            if state in TERMINAL:
                yield f"event: end\ndata: {json.dumps(read_json(d / 'status.json'))}\n\n"
                return
            await asyncio.sleep(0.3)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/jobs/{jid}/cancel")
async def cancel(jid: str):
    job_dir(jid)
    with WAKE:
        if jid in queue:
            queue.remove(jid)
            return update(jid, state="cancelled", outcome_summary="cancelled")
        running = current == jid
    if not running:
        raise HTTPException(409, "job is not queued or running")
    cancel_flag.set()
    for _ in range(40):  # the worker stops the group (SIGTERM, SIGKILL after 3 s) and records the state
        await asyncio.sleep(0.25)
        if read_json(JOBS / jid / "status.json")["state"] in TERMINAL:
            break
    return read_json(JOBS / jid / "status.json")


def example_names():
    return sorted(p.parent.name for p in EXAMPLES.glob("*/config.json") if not p.parent.name.startswith("_"))


@app.get("/api/examples")
def examples():
    return [dict(name=n, description=read_json(EXAMPLES / n / "config.json").get("description", ""), config=read_json(EXAMPLES / n / "config.json")) for n in example_names()]


@app.post("/api/examples/{name}/run")
def run_example(name: str):
    if name not in example_names():
        raise HTTPException(404, "no such example")
    src = EXAMPLES / name
    files = {f: (src / f).read_text() for f in ("gen.cpp", "ref.cpp", "sol.cpp", "checker.cpp") if (src / f).exists()}
    return new_job(files, read_json(src / "config.json"))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
