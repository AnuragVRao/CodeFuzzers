// History card: all jobs, newest first (refreshed every 5 s while one is queued or running).
import { useEffect, useState } from "react";
import { Badge, Card } from "../../ui.jsx";

export default function History({ onOpen, refreshKey }) {
  const [jobs, setJobs] = useState([]);
  const active = jobs.some((j) => j.state === "queued" || j.state === "running");
  useEffect(() => {
    const load = () => fetch("/api/jobs").then((r) => r.json()).then(setJobs).catch(() => {});
    load();
    if (!active) return undefined;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [active, refreshKey]);
  if (!jobs.length) return null;
  return (
    <Card title="History">
      <table>
        <thead><tr><th>started</th><th>state</th><th>budget</th><th>outcome</th></tr></thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id} className="click" onClick={() => onOpen(j.id)}>
              <td>{new Date(j.created).toLocaleString()}</td><td><Badge state={j.state} /></td>
              <td>{j.budget_s / 60} min</td><td>{j.outcome_summary ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
