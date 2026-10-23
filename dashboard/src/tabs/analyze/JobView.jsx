// Live view of one job: header (id, state, budget, elapsed + progress bar), the stage timeline and Cancel.
import { useEffect, useState } from "react";
import { Badge, Card, fmt } from "../../ui.jsx";
import { STAGES, TERMINAL, stageStates, useJob } from "./useJob.js";
import Report from "./Report.jsx";

const LABEL = { shrink: "shrink", clean: "clean bound", llm: "LLM explanation (after the budget)" };
const ICON = { pending: "○", running: "◔", done: "✓", failed: "✗", skipped: "–" };

export default function JobView({ id, onBack }) {
  const { job, events, position } = useJob(id);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(t); }, []);
  if (!job) return <p>Loading…</p>;

  const ended = TERMINAL.includes(job.state);
  const start = Date.parse(job.started ?? job.created), stop = job.finished ? Date.parse(job.finished) : now;
  const elapsed = job.state === "queued" ? 0 : Math.max(0, (stop - start) / 1000);
  const stages = stageStates(events, ended);
  const cancel = () => fetch(`/api/jobs/${id}/cancel`, { method: "POST" });

  return (
    <>
      <Card>
        <div className="jobhead">
          <button className="toggle" onClick={onBack}>← back</button>
          <code>{job.id}</code> <Badge state={job.state} />
          <span className="meta">budget {job.budget_s / 60} min · {job.state === "queued" ? `queue position ${position}` : `elapsed ${fmt(elapsed, 0)} s`}</span>
          {!ended && <button className="toggle cancel" onClick={cancel}>Cancel</button>}
        </div>
        <div className="bar"><div style={{ width: `${Math.min(100, (100 * elapsed) / job.budget_s)}%` }} /></div>
        <div className="timeline">
          {STAGES.map((s) => (
            <div key={s} className={`stage ${stages[s].state}`}>
              <span className="icon">{ICON[stages[s].state]}</span><b>{LABEL[s] ?? s}</b>
              <span className="meta">{stages[s].state === "skipped" ? "skipped" : stages[s].message.includes("\n") ? "see below" : stages[s].message}</span>
            </div>
          ))}
        </div>
      </Card>
      {ended && <Report job={job} />}
    </>
  );
}
