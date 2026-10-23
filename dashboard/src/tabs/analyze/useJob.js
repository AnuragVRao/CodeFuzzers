// Live state of one analysis job: status + report (polled while running), progress events (EventSource),
// and the queue position (derived from GET /api/jobs).
import { useEffect, useState } from "react";

export const TERMINAL = ["done", "failed", "cancelled", "timeout", "interrupted"];
export const STAGES = ["build", "validate", "calibrate", "sweep", "compare", "hunt", "shrink", "clean", "llm"];

export function useJob(id) {
  const [job, setJob] = useState(null);
  const [events, setEvents] = useState([]);
  const [position, setPosition] = useState(0);

  useEffect(() => {
    setJob(null); setEvents([]);
    let alive = true, timer;
    const load = async () => {
      const [j, all] = await Promise.all([fetch(`/api/jobs/${id}`).then((r) => r.json()), fetch("/api/jobs").then((r) => r.json())]);
      if (!alive) return;
      setJob(j);
      setPosition(all.filter((x) => x.state === "running" || (x.state === "queued" && x.id < id)).length);
      if (!TERMINAL.includes(j.state)) timer = setTimeout(load, 2000);
    };
    load().catch(() => {});
    const es = new EventSource(`/api/jobs/${id}/events`);
    es.onmessage = (m) => setEvents((ev) => (ev.length > Number(m.lastEventId) ? ev : [...ev, JSON.parse(m.data)]));
    es.addEventListener("end", () => { es.close(); load().catch(() => {}); });
    return () => { alive = false; clearTimeout(timer); es.close(); };
  }, [id]);

  return { job, events, position };
}

// Per-stage {state: pending|running|done|failed|skipped, message} derived from the event list.
export function stageStates(events, ended) {
  const out = Object.fromEntries(STAGES.map((s) => [s, { state: "pending", message: "" }]));
  for (const e of events) {
    const s = e.stage === "probe" ? "sweep" : e.stage;
    if (!out[s] || (e.stage === "probe" && e.status === "done")) continue;
    if (e.status === "info") out[s].message = e.message;
    else out[s] = { state: { start: "running", done: "done", fail: "failed", skip: "skipped" }[e.status], message: e.status === "start" ? "" : e.message };
  }
  for (const s of STAGES) if (ended && out[s].state === "pending") out[s].state = "skipped";
  return out;
}
