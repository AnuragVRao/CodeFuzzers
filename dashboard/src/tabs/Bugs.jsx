// Bugs tab: the gallery of planted bugs found by the fuzzer and shrunk. Filter by tier and group;
// click a card to see the shrunk input and both outputs, with differing tokens highlighted, and the
// local LLM's diagnosis (suggested line, category, explanation, fix) with ✓/✗ against the planted bug.
import { useState } from "react";
import { NoData, fmt, uniq } from "../ui.jsx";

const mark = (ok) => (ok ? <span className="ok">✓</span> : <span className="bad">✗</span>);

function LlmBox({ m, model }) {
  if (!m) return null;
  if (m.status !== "ok") return <div className="llm">{model}: {m.status === "too_long" ? "solution too long for the context window" : m.status}</div>;
  return (
    <div className="llm">
      <b>{model}</b> suggests line {m.line} {mark(m.line_ok)} · category {m.category} {mark(m.category_ok)} · {fmt(m.latency_s, 1)} s
      <div>{m.explanation}</div>
      <pre className="mono">{m.fix}</pre>
    </div>
  );
}

// Render `text` token by token; tokens that differ from `other` at the same (line, index) are marked.
function DiffText({ text, other }) {
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

function BugCard({ b, open, onToggle, model }) {
  const cut = (k) => (b[`${k}_truncated`] ? " (truncated)" : "");
  return (
    <div className={`card bug ${open ? "open" : ""}`} onClick={onToggle}>
      <h3>{b.problem}</h3>
      <div className="meta">
        <span className={`badge ${b.tier === "hard" ? "yes" : "no"}`}>{b.tier}</span> {b.group} · {b.kind} · {b.category}
      </div>
      <div>{b.description}</div>
      <div className="meta">Trigger: {b.trigger}</div>
      <div>size {b.size_original} → <b>{b.size_shrunk}</b> · bytes {b.bytes_original} → <b>{b.bytes_shrunk}</b></div>
      <button className="toggle" onClick={(e) => { e.stopPropagation(); onToggle(); }}>
        {open ? "Hide failing test ▴" : "Show failing test ▾"}
      </button>
      {open && (
        <div className="outputs" onClick={(e) => e.stopPropagation()}>
          <div>input{cut("input")}<pre className="mono">{b.input}</pre></div>
          <div>reference output{cut("ref_out")}<DiffText text={b.ref_out} other={b.fast_out} /></div>
          <div>buggy output{cut("fast_out")}<DiffText text={b.fast_out} other={b.ref_out} /></div>
        </div>
      )}
      {open && model && <LlmBox m={b.llm?.[model]} model={model} />}
    </div>
  );
}

export default function Bugs({ data }) {
  const rows = data.shrink?.gallery;
  const [tier, setTier] = useState("all");
  const [group, setGroup] = useState("all");
  const [open, setOpen] = useState(null);
  const models = Object.keys(data.llm || {}).filter((m) => data.llm[m].explain);
  const [chosen, setChosen] = useState(undefined);
  const model = models.includes(chosen) ? chosen : models[0];
  if (!rows?.length) return <NoData />;
  const pct = (x) => `${fmt(100 * x, 0)}%`;
  const shown = rows.filter((b) => (tier === "all" || b.tier === tier) && (group === "all" || b.group === group));
  const chip = (value, cur, set) => (
    <button key={value} className={`chip ${value === cur ? "on" : ""}`} onClick={() => set(value)}>{value}</button>
  );
  return (
    <>
      {models.length > 0 && (
        <div className="card llm-strip">
          {models.map((m) => {
            const e = data.llm[m].explain;
            const located = Math.round(e.line_acc * e.n_explained), cat = Math.round(e.category_acc * e.n_explained);
            return (
              <div key={m}>
                <b>{m}</b>: located {located}/{e.n_explained} bugs within ±3 lines (chance: {pct(e.chance_line_acc)},
                p = {fmt(e.line_p, 3)}) · category {cat}/{e.n_explained} (majority baseline “{e.majority_category}”:
                {" "}{pct(e.majority_share)}, p = {fmt(e.category_p, 3)}){e.n_too_long ? ` · ${e.n_too_long} too long` : ""}
              </div>
            );
          })}
          {models.length > 1 && (
            <label className="select">explanations shown from
              <select value={model} onChange={(ev) => setChosen(ev.target.value)}>
                {models.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
          )}
        </div>
      )}
      <div className="chips">
        {["all", "hard", "easy"].map((t) => chip(t, tier, setTier))}
        <span style={{ width: 16 }} />
        {["all", ...uniq(rows.map((b) => b.group))].map((g) => chip(g, group, setGroup))}
      </div>
      <div className="grid">
        {shown.map((b) => (
          <BugCard key={b.problem} b={b} model={model} open={open === b.problem}
            onToggle={() => setOpen(open === b.problem ? null : b.problem)} />
        ))}
      </div>
    </>
  );
}
