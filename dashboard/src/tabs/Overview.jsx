// Overview tab: the headline numbers from meta.headline, each with a small chart of the data behind it
// (hero: speed-up vs workers; pinning bars; one square per planted bug; per-bug shrink strip; shrinker
// speed-up sparkline), and the 5-step pipeline (essentials of the report's pipeline figure).
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, NoData, colorOf, fmt, uniq } from "../ui.jsx";

// Pipeline (essentials of the report's pipeline figure; every claim checked against the code), laid out as a snake:
// 1 -> 2, down to 3 (full width, the timed region), down to 4 -> 5.
const Arrow = ({ dir }) => (
  <div className={`arrow ${dir}`} aria-hidden="true">
    <svg viewBox="0 0 24 24"><path d="M2 12h18M14 6l6 6-6 6" /></svg>
  </div>
);
const Step = ({ n, name, where, timed, children }) => (
  <div className={`step${timed ? " timed" : ""}`}>
    <div className="step-head"><span className="num">{n}</span><b>{name}</b>
      {where && <code>{where}</code>}{timed && <span className="badge yes">timed region</span>}</div>
    {children}
  </div>
);
// Label / value rows; an array value renders as chips (joined by arrows when the row is a flow).
const Facts = ({ rows }) => (
  <dl className="facts">
    {rows.map(([k, v]) => [<dt key={`${k}-k`}>{k}</dt>,
      <dd key={`${k}-v`}>{Array.isArray(v) ? (
        <span className="chiprow">{v.map((c, i) => [k === "Flow" && i > 0 && <span className="flow-arrow" key={`a${c}`}>→</span>,
          <span className="pchip" key={c}>{c}</span>])}</span>) : v}</dd>])}
  </dl>
);
const LOOP = ["pick a recipe from the pool", "mutate: new size + fresh seed (or tape edits)", "generator → test input",
  "reference and fast solution → outputs", "compare → ok · WA · RE · TLE", "new coverage → add recipe to the pool"];
const POOLS = [["global", "1 mutex"], ["sharded", "16 mutexes"], ["rwlock", "shared_mutex"], ["snapshot", "copy-on-write swap"],
  ["noshare", "private pool per worker"]];

function Pipeline() {
  return (
    <div className="pipe">
      <Step n={1} name="Preparation">
        <Facts rows={[
          ["Problems", "30 from Library Checker: 12 array, 8 string, 5 graph, 5 tree"],
          ["Files", ["generator", "brute reference", "sol.cpp", "sol_bug.cpp", "verifier", "checker"]],
          ["Builds", <>linked with the fork-server runtime; coverage builds add <code>trace-pc</code></>],
        ]} />
      </Step>
      <Arrow dir="right" />
      <Step n={2} name="Control" where="tools/run.py">
        <Facts rows={[
          ["Plans", "strategy × workers × workload × repeat"],
          ["Order", "randomised blocks, discarded warm-up run"],
          ["Runs", "one at a time; collects the run JSON, never touches a test while the clock runs"],
        ]} />
      </Step>
      <div className="arrow-row to-right"><Arrow dir="down" /></div>
      <div className="wide">
        <Step n={3} name="Timed run" where="core/fuzzer.cpp" timed>
          <div className="timed-body">
            <div>
              <div className="sub-h">Worker loop <span>each thread pinned to one CPU</span></div>
              <ol className="loop">{LOOP.map((t) => <li key={t}>{t}</li>)}</ol>
              <div className="sub-n">hunt mode: the first bug stops all workers</div>
            </div>
            <div>
              <div className="sub-h">Fork-servers <span>own set per worker</span></div>
              <div className="stack">{["generator", "reference", "fast"].map((f) => <span key={f}>{f}</span>)}</div>
              <div className="sub-n">one forked child per test; coverage goes to a 64 KiB shared-memory edge map</div>
            </div>
            <div>
              <div className="sub-h">Shared pool <span>core/pool.hpp</span></div>
              <div className="stack">{POOLS.map(([k, d]) => <span key={k}><b>{k}</b><i>{d}</i></span>)}</div>
              <div className="sub-n">the only state shared between workers</div>
            </div>
          </div>
        </Step>
      </div>
      <div className="arrow-row to-left"><Arrow dir="down" /></div>
      <Step n={4} name="Shrinking">
        <Facts rows={[
          ["Input", "the first failing recipe"],
          ["Generator", "smaller sizes and fresh seeds, candidates run in parallel"],
          ["Tape", "truncate, delete, zero, reduce; then line and token ddmin"],
          ["Kept if", "the verifier accepts the input and the bug repeats"],
        ]} />
      </Step>
      <Arrow dir="right" />
      <Step n={5} name="Aggregation">
        <Facts rows={[
          ["Input", "per-run JSON (counts, rates, times)"],
          ["Flow", ["flatten.py", "runs.csv", "aggregate.py", "summary.json", "charts + dashboard"]],
          ["Statistics", "medians, IQR, Mann–Whitney U with Holm correction, bootstrap CIs"],
          ["LLM", "local Ollama explains shrunk bugs, outside the timed region"],
        ]} />
      </Step>
    </div>
  );
}

const median = (xs) => {
  const s = xs.filter((x) => x != null).sort((a, b) => a - b), n = s.length;
  return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null;
};
// Median of `key` per worker count over `rows` -> [{workers, value}], sorted by workers.
const byWorkers = (rows, key) =>
  uniq(rows.map((r) => r.workers)).sort((a, b) => a - b).map((w) => ({ workers: w, value: median(rows.filter((r) => r.workers === w).map((r) => r[key])) }));

// Hero: median speed-up over problems (realistic workload K=0, F=0) for rwlock and noshare, with the ideal line.
function SpeedupHero({ data, h }) {
  const k0 = data.scale.filter((r) => r.K === 0 && r.F === 0);
  const series = ["noshare", "rwlock"].map((s) => [s, byWorkers(k0.filter((r) => r.strategy === s), "speedup_abs")]);
  const rows = series[0][1].map(({ workers }) => ({
    workers, ideal: workers, ...Object.fromEntries(series.map(([s, pts]) => [s, pts.find((p) => p.workers === workers)?.value])),
  }));
  const close = h.speedup_20_rwlock_k0 && h.speedup_20_noshare_k0 &&
    Math.abs(h.speedup_20_rwlock_k0 - h.speedup_20_noshare_k0) / h.speedup_20_noshare_k0 < 0.05;
  return (
    <section className="card hero">
      <div className="hero-head">
        <div className="hero-value">{h.speedup_20_rwlock_k0 ? `${fmt(h.speedup_20_rwlock_k0, 1)}×` : "—"}</div>
        <div>
          <div className="label">speed-up at 20 workers with a shared pool (rwlock, realistic workload)</div>
          <div className="label sub">
            hardware ceiling (no sharing): {h.speedup_20_noshare_k0 ? `${fmt(h.speedup_20_noshare_k0, 1)}×` : "—"}
            {close && " — difference within run-to-run noise"}
          </div>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={210}>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: -16 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="workers" type="number" domain={[1, 20]} ticks={rows.map((r) => r.workers)} tickLine={false} />
          <YAxis domain={[0, 20]} ticks={[0, 5, 10, 15, 20]} tickLine={false} axisLine={false} />
          <Tooltip formatter={(v) => `${fmt(v, 1)}×`} labelFormatter={(w) => `${w} workers`} />
          <Legend verticalAlign="top" height={26} />
          <Line dataKey="ideal" stroke="var(--muted)" strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          {/* noshare as a wide translucent band under rwlock, so both stay visible where they overlap */}
          <Line dataKey="noshare" stroke={colorOf(data.meta, "noshare")} strokeWidth={8} strokeOpacity={0.35} dot={false}
            activeDot={false} isAnimationActive={false} />
          <Line dataKey="rwlock" stroke={colorOf(data.meta, "rwlock")} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <div className="label">median over problems; x = worker threads, y = throughput vs 1 worker. noshare is the wide band under rwlock.</div>
    </section>
  );
}

function Tile({ value, label, children }) {
  return (
    <div className="headline tile">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
      <div className="micro">{children}</div>
    </div>
  );
}

// Two thin bars: median tests/s pinned vs unpinned.
function PinningBars({ p }) {
  const max = Math.max(p.pinned.median, p.unpinned.median);
  return [["pinned", p.pinned.median, "var(--primary)"], ["unpinned", p.unpinned.median, "var(--muted)"]].map(([name, v, c]) => (
    <div className="hbar" key={name} title={`${name}: ${fmt(v, 0)} tests/s (median of ${p[name].values.length} runs)`}>
      <span>{name}</span>
      <div className="track"><div style={{ width: `${(100 * v) / max}%`, background: c }} /></div>
      <span>{fmt(v, 0)}/s</span>
    </div>
  ));
}

// One square per planted bug, grouped by problem group; filled = found, shrunk and re-validated.
function BugSquares({ gallery }) {
  return (
    <div className="bugsq">
      {uniq(gallery.map((g) => g.group)).map((group) => {
        const gs = gallery.filter((g) => g.group === group);
        return (
          <div key={group}>
            <div className="label">{group} {gs.filter((g) => g.mismatch_ok).length}/{gs.length}</div>
            <div className="squares">
              {gs.map((g) => (
                <span key={g.problem} className={g.mismatch_ok ? "on" : ""}
                  title={`${g.problem} (${g.tier}): ${g.mismatch_ok ? "found" : "not found"}`} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Strip of % of bytes kept per bug (0–100 %), with the median marked.
function ShrinkStrip({ gallery, med }) {
  const W = 260, x = (f) => 6 + f * (W - 12);
  return (
    <svg viewBox={`0 0 ${W} 52`} className="microsvg" role="img" aria-label="percent of input bytes kept per bug">
      <line x1={x(0)} x2={x(1)} y1={24} y2={24} stroke="var(--border)" strokeWidth={6} strokeLinecap="round" />
      {gallery.map((g) => {
        const f = g.bytes_shrunk / g.bytes_original;
        return (
          <circle key={g.problem} cx={x(f)} cy={24} r={4} fill="var(--primary)" fillOpacity={0.55}>
            <title>{`${g.problem}: ${g.bytes_original} → ${g.bytes_shrunk} bytes (${fmt(100 * f, 1)}% kept)`}</title>
          </circle>
        );
      })}
      {med != null && <line x1={x(med)} x2={x(med)} y1={14} y2={34} stroke="var(--fg)" strokeWidth={2} />}
      {med != null && <text x={x(med)} y={9} className="tick" textAnchor="middle">median {fmt(100 * med, 0)}%</text>}
      <text x={x(0)} y={50} className="tick">0%</text>
      <text x={x(1)} y={50} className="tick" textAnchor="end">100% of input bytes kept</text>
    </svg>
  );
}

// Sparkline: median shrinker speed-up over problems vs worker processes, with the ideal line.
function ShrinkSpark({ scaling }) {
  const pts = byWorkers(scaling, "speedup"), W = 260, H = 64;
  const maxW = Math.max(...pts.map((p) => p.workers), 1);
  const x = (w) => 6 + ((w - 1) / Math.max(maxW - 1, 1)) * (W - 12), y = (v) => H - 6 - (v / maxW) * (H - 12);
  const last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="microsvg" role="img" aria-label="shrinker speed-up vs worker processes">
      <line x1={x(1)} y1={y(1)} x2={x(maxW)} y2={y(maxW)} stroke="var(--muted)" strokeDasharray="4 3" />
      <polyline points={pts.map((p) => `${x(p.workers)},${y(p.value)}`).join(" ")} fill="none" stroke="var(--primary)" strokeWidth={2} />
      {pts.map((p) => (
        <circle key={p.workers} cx={x(p.workers)} cy={y(p.value)} r={3} fill="var(--primary)">
          <title>{`${p.workers} workers: ${fmt(p.value, 1)}×`}</title>
        </circle>
      ))}
      {last && <text x={x(last.workers)} y={y(last.value) + 14} className="tick" textAnchor="end">{fmt(last.value, 1)}× at {last.workers} workers</text>}
      <text x={x(1)} y={H} className="tick">1 worker</text>
      <text x={x(maxW * 0.7)} y={y(maxW * 0.7) - 5} className="tick" textAnchor="end">ideal</text>
    </svg>
  );
}

export default function Overview({ data }) {
  const m = data.meta;
  if (!m?.headline) return <NoData />;
  const h = m.headline, gallery = data.shrink?.gallery ?? [];
  return (
    <>
      <div className="overview">
        {data.scale?.length ? <SpeedupHero data={data} h={h} /> : <div />}
        <div className="tiles">
          <Tile value={h.pinning_ratio ? `+${fmt((h.pinning_ratio - 1) * 100, 0)}%` : "—"} label="throughput gain from CPU pinning (8 workers)">
            {data.pinning?.pinned && <PinningBars p={data.pinning} />}
          </Tile>
          <Tile value={`${h.bugs_found}/${h.bugs_total}`} label="planted bugs found, shrunk and re-validated">
            <BugSquares gallery={gallery} />
          </Tile>
          <Tile value={h.median_shrink_bytes_ratio != null ? `−${fmt((1 - h.median_shrink_bytes_ratio) * 100, 0)}%` : "—"}
            label="median input size reduction by the shrinker">
            <ShrinkStrip gallery={gallery} med={h.median_shrink_bytes_ratio} />
          </Tile>
          <Tile value={h.shrink_speedup_20 ? `${fmt(h.shrink_speedup_20, 1)}×` : "—"} label="shrinker speed-up at 20 worker processes">
            {data.shrink?.scaling?.length > 0 && <ShrinkSpark scaling={data.shrink.scaling} />}
          </Tile>
        </div>
      </div>
      <Card title="Pipeline"><Pipeline /></Card>
    </>
  );
}
