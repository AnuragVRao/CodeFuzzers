// Overview tab: five headline numbers from meta.headline, the 5-step pipeline of the project,
// and a footnote with the generation time, git commits and which presets the data comes from.
import { Card, NoData, fmt } from "../ui.jsx";

const STEPS = [
  ["Preparation", "Build binaries (fork-server runtime, trace-pc coverage) and calibrate planted bugs."],
  ["Control", "Sanity-check every problem: correct solution vs brute force, no false alarms."],
  ["Timed run", "W worker threads fuzz in parallel, sharing (or not) one pool of coverage recipes."],
  ["Shrinking", "Search generator space in parallel for the smallest input that still fails."],
  ["Aggregation", "Medians, IQRs, Mann–Whitney tests and charts from every recorded run."],
];

export default function Overview({ data }) {
  const m = data.meta;
  if (!m?.headline) return <NoData />;
  const h = m.headline;
  const at = h.max_speedup_at;
  const cards = [
    [`${fmt(h.max_speedup_abs, 2)}×`, `max absolute speed-up${at ? ` (${at.strategy}, ${at.workers} workers, ${at.problem})` : ""}`],
    [h.pinning_ratio ? `+${fmt((h.pinning_ratio - 1) * 100, 0)}%` : "—", "throughput gain from CPU pinning (8 workers)"],
    [`${h.bugs_found}/${h.bugs_total}`, "planted bugs found, shrunk and re-validated"],
    [h.median_shrink_bytes_ratio != null ? `−${fmt((1 - h.median_shrink_bytes_ratio) * 100, 0)}%` : "—", "median input size reduction by the shrinker"],
    [h.shrink_speedup_20 ? `${fmt(h.shrink_speedup_20, 1)}×` : "—", "shrinker speed-up at 20 worker processes"],
  ];
  return (
    <>
      <div className="headlines">
        {cards.map(([v, l]) => (
          <div className="headline" key={l}>
            <div className="value">{v}</div>
            <div className="label">{l}</div>
          </div>
        ))}
      </div>
      <Card title="Pipeline">
        <div className="pipeline">
          {STEPS.map(([name, text], i) => (
            <div className="step" key={name}><b>{i + 1}. {name}</b>{text}</div>
          ))}
        </div>
      </Card>
      <p className="footnote">
        Generated {m.generated_at} · commits {(m.commits || []).join(", ")} · presets:{" "}
        {Object.entries(m.preset || {}).map(([sec, p]) => (
          <span key={sec}>
            {sec}{" "}
            {p === "quick" ? <span className="badge warn">quick — preliminary</span> : <span className="badge yes">full</span>}{" "}
          </span>
        ))}
      </p>
    </>
  );
}
