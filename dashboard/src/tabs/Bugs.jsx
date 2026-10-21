// Bugs tab: the gallery of planted bugs found by the fuzzer and shrunk. Filter by tier and group;
// click a card to see the shrunk input and both outputs, with differing tokens highlighted.
import { useState } from "react";
import { NoData, uniq } from "../ui.jsx";

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

function BugCard({ b, open, onToggle }) {
  const cut = (k) => (b[`${k}_truncated`] ? " (truncated)" : "");
  return (
    <div className={`card bug ${open ? "open" : ""}`} onClick={open ? undefined : onToggle}>
      <h3 onClick={open ? onToggle : undefined}>{b.problem}</h3>
      <div className="meta">
        <span className={`badge ${b.tier === "hard" ? "yes" : "no"}`}>{b.tier}</span> {b.group} · {b.kind} · {b.category}
      </div>
      <div>{b.description}</div>
      <div className="meta">Trigger: {b.trigger}</div>
      <div>size {b.size_original} → <b>{b.size_shrunk}</b> · bytes {b.bytes_original} → <b>{b.bytes_shrunk}</b></div>
      {open && (
        <div className="outputs">
          <div>input{cut("input")}<pre className="mono">{b.input}</pre></div>
          <div>reference output{cut("ref_out")}<DiffText text={b.ref_out} other={b.fast_out} /></div>
          <div>buggy output{cut("fast_out")}<DiffText text={b.fast_out} other={b.ref_out} /></div>
        </div>
      )}
    </div>
  );
}

export default function Bugs({ data }) {
  const rows = data.shrink?.gallery;
  const [tier, setTier] = useState("all");
  const [group, setGroup] = useState("all");
  const [open, setOpen] = useState(null);
  if (!rows?.length) return <NoData />;
  const shown = rows.filter((b) => (tier === "all" || b.tier === tier) && (group === "all" || b.group === group));
  const chip = (value, cur, set) => (
    <button key={value} className={`chip ${value === cur ? "on" : ""}`} onClick={() => set(value)}>{value}</button>
  );
  return (
    <>
      <div className="chips">
        {["all", "hard", "easy"].map((t) => chip(t, tier, setTier))}
        <span style={{ width: 16 }} />
        {["all", ...uniq(rows.map((b) => b.group))].map((g) => chip(g, group, setGroup))}
      </div>
      <div className="grid">
        {shown.map((b) => (
          <BugCard key={b.problem} b={b} open={open === b.problem} onToggle={() => setOpen(open === b.problem ? null : b.problem)} />
        ))}
      </div>
    </>
  );
}
