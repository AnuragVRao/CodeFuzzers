// Scaling tab: strong-scaling results of the "scale" experiment. Pick a problem, a workload
// (extra pool ops K / write fraction F) and a metric; one line per strategy with IQR error bars,
// dashed reference lines (ideal speed-up, y=1 for efficiency and vs-noshare), and predicted
// throughput for the K=50/F=0.5 workload.
import { useState } from "react";
import { CartesianGrid, ErrorBar, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, NoData, ORDER, Select, colorOf, fmt, uniq } from "../ui.jsx";

const METRICS = {
  speedup: ["speed-up (throughput ratio, weak scaling)", (r) => r.tps_median / r.speedup_abs],
  efficiency: ["efficiency (speed-up / workers)", (r) => (r.tps_median / r.speedup_abs) * r.workers],
  throughput: ["throughput (tests / s)", () => 1],
  vs_noshare: ["throughput / noshare throughput", (r) => r.tps_median / r.vs_noshare],
};

export default function Scaling({ data }) {
  const rows = data.scale;
  const probs = uniq((rows || []).map((r) => r.problem));
  const [problem, setProblem] = useState(probs[0]);
  const [work, setWork] = useState("0/0");
  const [metric, setMetric] = useState("speedup");
  if (!rows?.length) return <NoData />;

  const mine = rows.filter((r) => r.problem === problem);
  const works = uniq(mine.map((r) => `${r.K}/${r.F}`));
  const wk = works.includes(work) ? work : works[0];
  const sel = mine.filter((r) => `${r.K}/${r.F}` === wk && r.speedup_abs != null);
  const workers = uniq(sel.map((r) => r.workers)).sort((a, b) => a - b);
  const strategies = ORDER.filter((s) => sel.some((r) => r.strategy === s));
  const [label, divisor] = METRICS[metric];
  const showPred = metric === "throughput" && wk === "50/0.5";

  const points = workers.map((w) => {
    const p = { workers: w, ideal: metric === "speedup" ? w : metric === "throughput" ? undefined : 1 };
    for (const r of sel.filter((r) => r.workers === w)) {
      const d = divisor(r);
      const y = r.tps_median / d;
      p[r.strategy] = y;
      p[`${r.strategy}_err`] = [Math.max(0, y - r.tps_q1 / d), Math.max(0, r.tps_q3 / d - y)];
      if (showPred) p[`${r.strategy}_pred`] = r.predicted_tps ?? undefined;
    }
    return p;
  });

  return (
    <Card title={`Scaling — ${problem}`}>
      <div className="row">
        <Select label="problem" value={problem} options={probs} onChange={setProblem} />
        <Select label="workload (K extra ops / F write fraction)" value={wk}
          options={works.map((w) => ({ value: w, label: `K=${w.split("/")[0]}, F=${w.split("/")[1]}` }))} onChange={setWork} />
        <Select label="metric" value={metric} onChange={setMetric}
          options={[{ value: "speedup", label: "absolute speed-up" }, { value: "efficiency", label: "efficiency" },
            { value: "throughput", label: "throughput" }, { value: "vs_noshare", label: "vs noshare (sharing cost)" }]} />
      </div>
      <ResponsiveContainer width="100%" height={380}>
        <LineChart data={points} margin={{ top: 10, right: 30, bottom: 25, left: 20 }}>
          <CartesianGrid stroke="#eee" />
          <XAxis dataKey="workers" type="number" ticks={workers} domain={["dataMin", "dataMax"]}
            label={{ value: "workers (threads)", position: "insideBottom", offset: -15 }} />
          <YAxis label={{ value: label, angle: -90, position: "insideLeft", offset: 0, style: { textAnchor: "middle" } }}
            tickFormatter={(v) => fmt(v, 2)} width={80} />
          <Tooltip formatter={(v) => fmt(v, 2)} />
          <Legend verticalAlign="top" />
          {metric !== "throughput" && (
            <Line dataKey="ideal" name={metric === "speedup" ? "ideal" : "reference (1.0)"} stroke="#999" strokeDasharray="6 4" dot={false} />
          )}
          {strategies.map((s) => (
            <Line key={s} dataKey={s} name={s} stroke={colorOf(data.meta, s)} strokeWidth={2} isAnimationActive={false}>
              <ErrorBar dataKey={`${s}_err`} width={4} stroke={colorOf(data.meta, s)} />
            </Line>
          ))}
          {showPred && strategies.map((s) => (
            <Line key={`${s}_pred`} dataKey={`${s}_pred`} name={`${s} predicted`} stroke={colorOf(data.meta, s)}
              strokeDasharray="5 5" dot={false} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="explain">
        Compare each strategy with noshare (navy), not with the ideal line. noshare shares nothing, so its curve is the
        hardware limit (hyper-threads, efficiency cores, process start-up). The gap between a strategy and noshare is the
        cost of sharing the pool. Scale runs use identical random recipes for every strategy, so all of them do the same
        work per test.
      </p>
    </Card>
  );
}
