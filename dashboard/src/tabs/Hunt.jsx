// Hunt tab: how fast each strategy finds the planted bug (hard-tier problems). Median
// tests-to-bug per strategy with IQR and every individual run, the Mann–Whitney comparisons
// (Holm-corrected), and how time-to-bug scales with the number of workers.
import { useState } from "react";
import { Bar, CartesianGrid, Cell, ComposedChart, ErrorBar, Legend, Line, LineChart, ResponsiveContainer, Scatter,
  Tooltip, XAxis, YAxis } from "recharts";
import { Card, NoData, ORDER, Select, colorOf, fmt, uniq } from "../ui.jsx";

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
  const bars = sel.map((r) => ({
    strategy: r.strategy,
    median: r.tests_median != null ? Math.max(r.tests_median, 0.5) : null,
    err: r.tests_median != null && r.tests_q1 != null && r.tests_q3 != null
      ? [Math.max(0, r.tests_median - r.tests_q1), Math.max(0, r.tests_q3 - r.tests_median)] : [0, 0],
  }));
  const dots = sel.flatMap((r) => r.values.filter((v) => v != null).map((v) => ({ strategy: r.strategy, run: Math.max(v, 0.5) })));
  const censored = sel.map((r) => `${r.strategy}: ${r.censored}`).join(", ");
  const tests = (data.hunt_tests || []).filter((t) => t.problem === problem);
  const scaling = data.hunt_time_scaling || [];
  const sw = uniq(scaling.map((r) => r.workers)).sort((a, b) => a - b);
  const tsPoints = sw.map((x) => Object.fromEntries([["workers", x],
    ...scaling.filter((r) => r.workers === x).map((r) => [r.strategy, r.geomean_time_median])]));

  return (
    <>
      <Card title={`Tests until first bug — ${problem}`}>
        <div className="row">
          <Select label="problem (hard tier)" value={problem} options={probs} onChange={setProblem} />
          <Select label="workers" value={w} options={ws} onChange={setWorkers} />
        </div>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={bars} margin={{ top: 10, right: 30, bottom: 25, left: 20 }}>
            <CartesianGrid stroke="#eee" />
            <XAxis dataKey="strategy" type="category" allowDuplicatedCategory={false}
              label={{ value: "strategy", position: "insideBottom", offset: -15 }} />
            <YAxis scale="log" domain={[0.5, "auto"]} allowDataOverflow width={80}
              label={{ value: "tests before bug (log)", angle: -90, position: "insideLeft", style: { textAnchor: "middle" } }} />
            <Tooltip formatter={(v) => fmt(v, 0)} />
            <Legend verticalAlign="top" />
            <Bar dataKey="median" name="median (IQR)" fillOpacity={0.75} isAnimationActive={false}>
              {bars.map((b) => <Cell key={b.strategy} fill={colorOf(data.meta, b.strategy)} />)}
              <ErrorBar dataKey="err" width={6} stroke="#333" />
            </Bar>
            <Scatter data={dots} dataKey="run" name="individual runs" fill="#333" isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="explain">Runs without a bug before the time limit (censored) — {censored}.</p>
      </Card>
      <Card title="Statistical comparisons (Mann–Whitney U, Holm-corrected)">
        {tests.length ? (
          <table>
            <thead><tr><th>workers</th><th>comparison</th><th>median a</th><th>median b</th><th>ratio b/a</th><th>p (Holm)</th><th /></tr></thead>
            <tbody>
              {tests.map((t) => (
                <tr key={`${t.workers}${t.comparison}`}>
                  <td>{t.workers}</td><td>{t.comparison}: {t.a} vs {t.b}</td><td>{fmt(t.median_a, 0)}</td>
                  <td>{fmt(t.median_b, 0)}</td><td>{fmt(t.ratio, 2)}</td><td>{fmt(t.p_holm, 3)}</td>
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
              <YAxis width={80} tickFormatter={(v) => fmt(v, 3)}
                label={{ value: "median time to bug (s)", angle: -90, position: "insideLeft", style: { textAnchor: "middle" } }} />
              <Tooltip formatter={(v) => fmt(v, 4)} />
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
