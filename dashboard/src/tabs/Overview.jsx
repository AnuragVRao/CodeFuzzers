// Overview tab: five headline numbers from meta.headline, the 5-step pipeline of the project,
// and a footnote with the generation time, git commits and which presets the data comes from.
import { Card, NoData, fmt } from "../ui.jsx";

const STEPS = [
  ["Preparation", "Library Checker problems curated and bundled (generator, brute reference, fast solution, checker); lightweight and path-tracking builds."],
  ["Control", "Python orchestrator varies workers, strategy, read/write mix and seed; pins cores; repeats every run."],
  ["Timed run", "Workers take a recipe from the shared pool, generate the test, run reference and fast solution, compare, and add recipes that reach new coverage."],
  ["Shrinking", "Parallel generator-space shrinking finds the smallest input that still fails, then re-validates it."],
  ["Aggregation", "Medians, IQRs and Mann–Whitney tests across workers, strategies and workloads; charts for speed-up, efficiency and time to bug. A local LLM (Ollama) explains shrunk failures and drafts generators, outside the timed region."],
];

export default function Overview({ data }) {
  const m = data.meta;
  if (!m?.headline) return <NoData />;
  const h = m.headline;
  const cards = [
    [h.speedup_20_rwlock_k0 ? `${fmt(h.speedup_20_rwlock_k0, 1)}×` : "—", "speed-up at 20 workers (rwlock, realistic workload)",
      `hardware ceiling (no sharing): ${h.speedup_20_noshare_k0 ? `${fmt(h.speedup_20_noshare_k0, 1)}×` : "—"}` +
        (h.speedup_20_rwlock_k0 && h.speedup_20_noshare_k0 &&
         Math.abs(h.speedup_20_rwlock_k0 - h.speedup_20_noshare_k0) / h.speedup_20_noshare_k0 < 0.05
          ? " — difference within run-to-run noise" : "")],
    [h.pinning_ratio ? `+${fmt((h.pinning_ratio - 1) * 100, 0)}%` : "—", "throughput gain from CPU pinning (8 workers)"],
    [`${h.bugs_found}/${h.bugs_total}`, "planted bugs found, shrunk and re-validated"],
    [h.median_shrink_bytes_ratio != null ? `−${fmt((1 - h.median_shrink_bytes_ratio) * 100, 0)}%` : "—", "median input size reduction by the shrinker"],
    [h.shrink_speedup_20 ? `${fmt(h.shrink_speedup_20, 1)}×` : "—", "shrinker speed-up at 20 worker processes"],
  ];
  return (
    <>
      <div className="headlines">
        {cards.map(([v, l, sub]) => (
          <div className="headline" key={l}>
            <div className="value">{v}</div>
            <div className="label">{l}</div>
            {sub && <div className="label sub">{sub}</div>}
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
