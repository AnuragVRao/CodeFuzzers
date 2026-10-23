// Analyze tab: talks to the analysis server (tools/server.py, proxied under /api). Shows the new-analysis cards
// and the history, or the live view / report of one job. Without a server only a hint card is shown.
import { useEffect, useState } from "react";
import { Card } from "../ui.jsx";
import History from "./analyze/History.jsx";
import JobView from "./analyze/JobView.jsx";
import NewJob from "./analyze/NewJob.jsx";

export default function Analyze() {
  const [examples, setExamples] = useState(undefined); // undefined = loading, null = server not running
  const [jobId, setJobId] = useState(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    fetch("/api/examples").then((r) => (r.ok ? r.json() : Promise.reject())).then(setExamples).catch(() => setExamples(null));
  }, []);

  if (examples === undefined) return <p>Loading…</p>;
  if (examples === null)
    return (
      <Card>
        <p>Analysis server is not running. Start it with:</p>
        <pre className="mono">python3 tools/server.py</pre>
      </Card>
    );
  const open = (id) => { setJobId(id); setRefresh((n) => n + 1); };
  return jobId ? (
    <JobView id={jobId} onBack={() => open(null)} />
  ) : (
    <>
      <NewJob examples={examples} onStarted={open} />
      <History onOpen={open} refreshKey={refresh} />
    </>
  );
}
