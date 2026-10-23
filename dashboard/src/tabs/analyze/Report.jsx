// Report of a finished job: verdict banner, mode / battery banners, failing test (diff highlighted), LLM
// suggestion with source context, calibration chart, performance (sweep + compare) and hunt statistics.
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, DiffText, fmt } from "../../ui.jsx";

function Verdict({ job, rep }) {
  const fb = rep?.hunt?.first_bug;
  if (rep?.bug)
    return <div className="banner bug"><b>Bug found: {rep.bug.kind} after {fb.tests_before + 1} tests ({fmt(fb.time_s, 3)} s)</b></div>;
  if (rep?.clean_bound) return <div className="banner clean"><b>No bug found</b><div>{rep.clean_bound.sentence}</div></div>;
  if (job.state !== "failed") return <div className="banner fail"><b>Analysis {job.state}</b></div>;
  const stage = (job.outcome_summary ?? "").replace("failed: ", "") || "unknown stage";
  const error = (job.error ?? "").replace(/\/[^:\n]*?\/results\/jobs\/[^/\s]+\//g, ""); // job dir prefix is noise
  const multi = error.includes("\n");
  return (
    <div className="banner fail">
      <b>Analysis failed at {stage}{multi ? "" : `: ${error}`}</b>
      {multi && <pre className="mono">{error}</pre>}
    </div>
  );
}

function FailingTest({ bug }) {
  return (
    <Card title="Failing test">
      <div>{bug.original.size != null && <>size {bug.original.size} → <b>{bug.shrunk.size}</b> · </>}bytes {bug.original.bytes} → <b>{bug.shrunk.bytes}</b> · {bug.tests_used} shrink tests</div>
      <div className="outputs">
        <div>input<pre className="mono">{bug.input}</pre></div>
        <div>reference output<DiffText text={bug.ref_out} other={bug.fast_out} /></div>
        <div>solution output<DiffText text={bug.fast_out} other={bug.ref_out} /></div>
      </div>
    </Card>
  );
}

function LlmCard({ id, llm }) {
  const [lines, setLines] = useState([]);
  useEffect(() => {
    fetch(`/api/jobs/${id}/files/sol.cpp`).then((r) => r.text()).then((t) => setLines(t.split("\n"))).catch(() => {});
  }, [id]);
  const { line, category, explanation, fix } = llm.answer;
  const from = Math.max(1, line - 5), shown = lines.slice(from - 1, line + 5);
  return (
    <Card title={`Unverified suggestion (${llm.model})`}>
      <div>Suggested line <b>{line}</b> · category <b>{category}</b></div>
      <p>{explanation}</p>
      <pre className="mono">{fix}</pre>
      {shown.length > 0 && (
        <pre className="mono code">{shown.map((t, i) => <span key={i} className={from + i === line ? "ln hl" : "ln"}>{String(from + i).padStart(4)}| {t}</span>)}</pre>
      )}
      <div className="meta">{llm.evaluation_note}</div>
    </Card>
  );
}

function Chart({ data, x, lines, log, mark, ticks }) {
  return (
    <ResponsiveContainer width="100%" height={230}>
      <LineChart data={data} margin={{ left: 0, right: 16, top: 8 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={x} type="number" ticks={ticks} scale={log ? "log" : "auto"} domain={log ? [1, "dataMax"] : ["dataMin", "dataMax"]} />
        <YAxis scale={log ? "log" : "auto"} domain={log ? [0.1, "auto"] : [0, "auto"]} width={50} />
        <Tooltip /><Legend />
        {mark && <ReferenceLine x={mark} stroke="#c0392b" label={{ value: "max_size", fontSize: 11 }} />}
        {lines.map(([key, color, dash]) => <Line key={key} dataKey={key} stroke={color} strokeDasharray={dash} dot={!dash} isAnimationActive={false} />)}
      </LineChart>
    </ResponsiveContainer>
  );
}

export default function Report({ job }) {
  const rep = job.report;
  const href = useMemo(() => rep && URL.createObjectURL(new Blob([JSON.stringify(rep, null, 1)], { type: "application/json" })), [rep]);
  if (!rep) return <Verdict job={job} rep={null} />;
  const seedOnly = rep.mode?.mode === "seed-only";
  const cal = (rep.calibration?.table ?? []).filter((r) => r.size).map((r) => ({ size: r.size, "reference ms": Math.max(0.1, r.ref_median_ms) }));
  const sweep = (rep.sweep ?? []).map((r) => ({ workers: r.workers, "speed-up": r.speedup, ideal: r.workers }));
  const h = rep.hunt, c = rep.compare;
  return (
    <>
      <Verdict job={job} rep={rep} />
      {seedOnly && <div className="banner note">Seed-only mode ({rep.mode.reason}): calibration, guided search and size shrinking are disabled.</div>}
      {(rep.warnings ?? []).map((w) => <div key={w} className="banner warn">{w}</div>)}
      {rep.bug && <FailingTest bug={rep.bug} />}
      {rep.llm && <LlmCard id={job.id} llm={rep.llm} />}
      {cal.length > 0 && <Card title="Calibration"><Chart data={cal} x="size" log mark={rep.calibration.max_size} lines={[["reference ms", "#0e8a8a"]]} />
        <div className="meta">reference median time per input vs generator size (log–log); sizes above max_size are not fuzzed</div></Card>}
      {sweep.length > 0 && (
        <Card title="Performance">
          <Chart data={sweep} x="workers" ticks={sweep.map((r) => r.workers)} lines={[["speed-up", "#0e8a8a"], ["ideal", "#888", "5 4"]]} />
          {c && <div>At {c.workers} workers: noshare {fmt(c.median.noshare, 0)} tests/s vs rwlock {fmt(c.median.rwlock, 0)} tests/s — ratio <b>{c.ratio_rwlock_vs_noshare}</b>
            <div className="meta">{c.note}</div></div>}
          <div className="meta">{rep.perf_note}</div>
        </Card>
      )}
      {h && <Card title="Hunt statistics"><div className="stats">
        <span>tests <b>{fmt(h.tests, 0)}</b></span><span>tests/s <b>{fmt(h.tests_per_sec, 0)}</b></span><span>coverage features <b>{h.cov_features}</b></span>
        <span>{Object.entries(h.outcomes).map(([k, v]) => `${k} ${v}`).join(" · ")}</span></div></Card>}
      <a href={href} download="report.json">Download report.json</a>
    </>
  );
}
