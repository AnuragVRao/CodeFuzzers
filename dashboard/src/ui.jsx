// Small shared UI pieces for the tabs: the "No data yet" placeholder, a labelled <select>,
// a section card, DiffText (token-wise diff highlighting), a state badge, number formatting and the strategy colour lookup (from meta.strategy_colors).

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

// Render `text` token by token; tokens that differ from `other` at the same (line, index) are marked.
export function DiffText({ text, other }) {
  const otherLines = other.split("\n").map((l) => l.split(/\s+/).filter(Boolean));
  return (
    <pre className="mono">
      {text.split("\n").map((line, i) => {
        let k = 0;
        return (
          <span key={i}>
            {line.split(/(\s+)/).map((tok, j) => {
              if (!tok || /^\s+$/.test(tok)) return tok;
              const same = otherLines[i]?.[k++] === tok;
              return same ? tok : <mark key={j} className="diff">{tok}</mark>;
            })}
            {"\n"}
          </span>
        );
      })}
    </pre>
  );
}

const BADGE = { done: "yes", running: "run", failed: "bad", timeout: "bad", interrupted: "bad" };
export const Badge = ({ state }) => <span className={`badge ${BADGE[state] ?? "no"}`}>{state}</span>;
