// Hunt tab: how fast each strategy finds the planted bug (hard-tier problems). Dot plot of
// tests-to-bug per strategy (median line, IQR whisker, every run as a jittered dot, censored
// runs as "x" at the top), the Mann–Whitney comparisons, and time-to-bug vs workers.
import { useState } from "react";
import { CartesianGrid, LabelList, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis } from "recharts";
import { Card, NoData, ORDER, Select, colorOf, fmt, uniq } from "../ui.jsx";

// Powers of ten (and 2x, 5x when the range is narrow) inside [lo, hi], for readable log axes.
function logTicks(lo, hi) {
  const t = [];
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++)
    for (const m of hi / lo < 100 ? [1, 2, 5] : [1]) {
      const v = m * 10 ** e;
      if (v >= lo && v <= hi) t.push(v);
    }
  return t;
}

const jitter = (k) => (((k * 0.618034) % 1) - 0.5) * 0.36; // deterministic, by run index

export default function Hunt({ data }) {
  const rows = data.hunt;
  const probs = uniq((rows || []).map((r) => r.problem));
  const [problem, setProblem] = useState(probs[0]);
  const [workers, setWorkers] = useState(undefined);
  if (!rows?.length) return <NoData />;

  const mine = rows.filter((r) => r.problem === problem);
  const ws = uniq(mine.map((r) => r.workers)).sort((a, b) => a - b);
  const w = ws.includes(Number(workers)) ? Number(workers) : ws[0];
  const sel = ORDER.map((s) => mine.find((r) => r.strategy === s && r.workers === w)).filter(Boolean);
  const pos = (v) => Math.max(v, 1); // tests_to_bug is always >= 1
  const plotted = sel.flatMap((r) => [...r.values.filter((v) => v != null), r.tests_to_bug_q1, r.tests_to_bug_q3]
    .filter((v) => v != null).map(pos));
  const lo = Math.min(...plotted, 1) / 2;
  const hi = Math.max(...plotted, 1) * 2;
  const top = hi / 1.4; // where censored runs are drawn

  const fam = (t) => (t.family === "confirmatory" ? 0 : 1);
  const tests = (data.hunt_tests || []).filter((t) => t.problem === problem).sort((a, b) => fam(a) - fam(b));
  const mde = data.power?.mde_ratio;
  const scaling = data.hunt_time_scaling || [];
  const sw = uniq(scaling.map((r) => r.workers)).sort((a, b) => a - b);
  const tsPoints = sw.map((x) => Object.fromEntries([["workers", x],
    ...scaling.filter((r) => r.workers === x && r.geomean_time_median).map((r) => [r.strategy, r.geomean_time_median * 1000])]));
  const msVals = tsPoints.flatMap((p) => Object.entries(p).filter(([k]) => k !== "workers").map(([, v]) => v));
  const msLo = Math.min(...msVals, 1) / 2, msHi = Math.max(...msVals, 1) * 2;

  return (
    <>
      <Card title={`Tests until first bug — ${problem}, ${w} workers`}>
        <div className="row">
          <Select label="problem (hard tier)" value={problem} options={probs} onChange={setProblem} />
          <Select label="workers" value={w} options={ws} onChange={setWorkers} />
        </div>
        <ResponsiveContainer width="100%" height={340}>
          <ScatterChart margin={{ top: 20, right: 30, bottom: 25, left: 20 }}>
            <CartesianGrid stroke="#eee" />
            <XAxis type="number" dataKey="x" domain={[-0.6, sel.length - 0.4]} ticks={sel.map((_, i) => i)}
              tickFormatter={(i) => sel[i]?.strategy ?? ""} label={{ value: "strategy", position: "insideBottom", offset: -15 }} />
            <YAxis type="number" dataKey="y" scale="log" domain={[lo, hi]} ticks={logTicks(lo, hi)} allowDataOverflow
              tickFormatter={(v) => fmt(v, 1)} width={80}
              label={{ value: "tests until first bug (incl. the failing one)", angle: -90, position: "insideLeft", style: { textAnchor: "middle" } }} />
            <Tooltip formatter={(v, n) => (n === "y" ? fmt(v, 0) : null)} />
            <Legend verticalAlign="top" />
            {sel.map((r, i) => (
              <Scatter key={r.strategy} name={r.strategy} fill={colorOf(data.meta, r.strategy)} isAnimationActive={false}
                data={r.values.map((v, k) => (v == null ? null : { x: i + jitter(k), y: pos(v) })).filter(Boolean)} />
            ))}
            {sel.map((r, i) => r.tests_to_bug_q1 != null && r.tests_to_bug_q3 != null && (
              <ReferenceLine key={`iqr${i}`} segment={[{ x: i, y: pos(r.tests_to_bug_q1) }, { x: i, y: pos(r.tests_to_bug_q3) }]}
                stroke="#333" strokeWidth={2} />
            ))}
            {sel.map((r, i) => r.tests_to_bug_median != null && (
              <ReferenceLine key={`med${i}`} segment={[{ x: i - 0.28, y: pos(r.tests_to_bug_median) }, { x: i + 0.28, y: pos(r.tests_to_bug_median) }]}
                stroke="#111" strokeWidth={3} />
            ))}
            <Scatter name="censored (no bug before time limit)" shape="cross" fill="#C0392B" isAnimationActive={false}
              data={sel.flatMap((r, i) => r.values.map((v, k) => (v == null ? { x: i + jitter(k), y: top, label: "censored" } : null)).filter(Boolean))}>
              <LabelList dataKey="label" position="top" fontSize={11} />
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
        <p className="explain">Dots are individual runs; the thick bar is the median and the vertical line the interquartile range.</p>
      </Card>
      <Card title="Statistical comparisons (Mann–Whitney U, Holm-corrected)">
        {mde && (
          <p className="explain">
            With 30 runs per group we can detect a ≥ {fmt(mde["30"], 1)}× difference (80% power); with 100 runs, ≥ {fmt(mde["100"], 1)}×.
          </p>
        )}
        {tests.length ? (
          <table>
            <thead><tr><th>family</th><th>workers</th><th>comparison</th><th>median a</th><th>median b</th><th>ratio b/a</th>
              <th>95% CI</th><th>p (Holm)</th><th /></tr></thead>
            <tbody>
              {tests.map((t) => (
                <tr key={`${t.family}${t.workers}${t.comparison}`}>
                  <td>{t.family}</td><td>{t.workers}</td><td>{t.comparison}: {t.a} vs {t.b}</td><td>{fmt(t.median_a, 0)}</td>
                  <td>{fmt(t.median_b, 0)}</td><td>{fmt(t.ratio, 2)}</td>
                  <td>[{fmt(t.ratio_ci_lo, 2)} – {fmt(t.ratio_ci_hi, 2)}]</td><td>{fmt(t.p_holm, 3)}</td>
                  <td>{t.p_holm < 0.05 ? <span className="badge yes">significant</span> : <span className="badge no">not significant</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <NoData />}
      </Card>
      <Card title="Time to first bug vs workers (geometric mean over hard-tier problems)">
        {tsPoints.length ? (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={tsPoints} margin={{ top: 10, right: 30, bottom: 25, left: 20 }}>
              <CartesianGrid stroke="#eee" />
              <XAxis dataKey="workers" type="number" ticks={sw} domain={["dataMin", "dataMax"]}
                label={{ value: "workers (threads)", position: "insideBottom", offset: -15 }} />
              <YAxis scale="log" domain={[msLo, msHi]} ticks={logTicks(msLo, msHi)} allowDataOverflow width={80}
                tickFormatter={(v) => fmt(v, 1)}
                label={{ value: "median time to bug (ms, log)", angle: -90, position: "insideLeft", style: { textAnchor: "middle" } }} />
              <Tooltip formatter={(v) => `${fmt(v, 2)} ms`} />
              <Legend verticalAlign="top" />
              {ORDER.filter((s) => scaling.some((r) => r.strategy === s)).map((s) => (
                <Line key={s} dataKey={s} stroke={colorOf(data.meta, s)} strokeWidth={2} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : <NoData />}
      </Card>
    </>
  );
}
