// Shrinking tab: speed-up of the parallel (process-pool) shrinker per problem vs worker count,
// and the gallery sorted by how much the shrinker reduced each failing input.
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, NoData, fmt, uniq } from "../ui.jsx";

const LINE_COLORS = ["#0E8A8A", "#C0392B", "#7D3C98", "#E0A030", "#1B2A4A"];

export default function Shrinking({ data }) {
  const sc = data.shrink?.scaling || [];
  const gallery = data.shrink?.gallery || [];
  if (!sc.length && !gallery.length) return <NoData />;
  const probs = uniq(sc.map((r) => r.problem));
  const ws = uniq(sc.map((r) => r.workers)).sort((a, b) => a - b);
  const points = ws.map((w) => Object.fromEntries([["workers", w], ["ideal", w],
    ...sc.filter((r) => r.workers === w).map((r) => [r.problem, r.speedup])]));
  const sorted = [...gallery].sort((a, b) => a.bytes_shrunk / a.bytes_original - b.bytes_shrunk / b.bytes_original);

  return (
    <>
      <Card title="Shrinker speed-up (process pool)">
        {sc.length ? (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={points} margin={{ top: 10, right: 30, bottom: 25, left: 20 }}>
              <CartesianGrid stroke="#eee" />
              <XAxis dataKey="workers" type="number" ticks={ws} domain={["dataMin", "dataMax"]}
                label={{ value: "worker processes", position: "insideBottom", offset: -15 }} />
              <YAxis width={70} label={{ value: "speed-up vs 1 worker (×)", angle: -90, position: "insideLeft", style: { textAnchor: "middle" } }} />
              <Tooltip formatter={(v) => fmt(v, 2)} />
              <Legend verticalAlign="top" />
              <Line dataKey="ideal" stroke="#999" strokeDasharray="6 4" dot={false} />
              {probs.map((p, i) => (
                <Line key={p} dataKey={p} stroke={LINE_COLORS[i % LINE_COLORS.length]} strokeWidth={2} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : <NoData />}
      </Card>
      <Card title="Shrink results (sorted by remaining size)">
        <table>
          <thead><tr><th>problem</th><th>tier</th><th>size</th><th>bytes</th><th>kept</th><th>tests</th><th>time</th></tr></thead>
          <tbody>
            {sorted.map((g) => (
              <tr key={g.problem}>
                <td>{g.problem}</td><td>{g.tier}</td><td>{g.size_original} → {g.size_shrunk}</td>
                <td>{g.bytes_original} → {g.bytes_shrunk}</td><td>{fmt((100 * g.bytes_shrunk) / g.bytes_original, 1)}%</td>
                <td>{g.tests_used}</td><td>{fmt(g.wall_s, 1)} s</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}
