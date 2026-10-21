// Small shared UI pieces for the tabs: the "No data yet" placeholder, a labelled <select>,
// a section card, number formatting and the strategy colour lookup (from meta.strategy_colors).

export const ORDER = ["random", "noshare", "global", "sharded", "rwlock", "snapshot"];

export function NoData() {
  return <div className="nodata">No data yet — run tools/aggregate.py</div>;
}

export function Select({ label, value, options, onChange }) {
  return (
    <label className="select">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={String(o.value ?? o)} value={o.value ?? o}>{o.label ?? o}</option>
        ))}
      </select>
    </label>
  );
}

export function Card({ title, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {title && <h2>{title}</h2>}
      {children}
    </section>
  );
}

export const fmt = (x, digits = 1) =>
  x == null || Number.isNaN(x) ? "—" : Number(x).toLocaleString(undefined, { maximumFractionDigits: digits });

export const colorOf = (meta, s) => meta?.strategy_colors?.[s] ?? "#888";

export const uniq = (xs) => [...new Set(xs)];
