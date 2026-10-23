// "New analysis" card: one button per example, plus the upload form (files, checker mode, generator
// argument template with the server's validation rules, budget). Calls onStarted(jobId) after a POST.
import { useState } from "react";
import { Card } from "../../ui.jsx";

const PRESETS = ["{seed} {size}", "{seed}", "-seed {seed} -n {size}"];
const PRESET_NAMES = ["{seed} {size}  (default)", "{seed}  (seed only)", "-seed {seed} -n {size}  (testlib-style)"];
const BUDGETS = [[60, "1 min"], [180, "3 min"], [600, "10 min"]];
const FILES = [["gen", "Generator"], ["ref", "Reference (brute force)"], ["sol", "Solution under test"]];

// Same rules as the server: a whole {seed} token; no token that merely contains {seed} / {size}.
export function templateError(t) {
  const toks = t.trim().split(/\s+/).filter(Boolean);
  const bad = toks.find((x) => x !== "{seed}" && x !== "{size}" && (x.includes("{seed}") || x.includes("{size}")));
  if (bad) return `"${bad}" must be exactly {seed} or {size}, not merely contain it`;
  return toks.includes("{seed}") ? null : "needs a whole {seed} argument";
}

const kb = (n) => `${(n / 1024).toFixed(1)} KB`;

export default function NewJob({ examples, onStarted }) {
  const [files, setFiles] = useState({});
  const [custom, setCustom] = useState(false);
  const [template, setTemplate] = useState(PRESETS[0]);
  const [budget, setBudget] = useState(180);
  const [error, setError] = useState(null);
  const fileList = custom ? [...FILES, ["checker", "Checker (testlib)"]] : FILES;
  const tErr = templateError(template);
  const big = fileList.find(([k]) => files[k]?.size > 1 << 20);
  const valid = !tErr && !big && fileList.every(([k]) => files[k]);

  const post = async (url, body) => {
    setError(null);
    const r = await fetch(url, { method: "POST", body });
    const j = await r.json();
    if (!r.ok) return setError(j.detail ?? "request failed");
    onStarted(j.id);
  };
  const submit = () => {
    const f = new FormData();
    fileList.forEach(([k]) => f.append(k, files[k]));
    f.append("checker_mode", custom ? "custom" : "exact");
    f.append("gen_template", template.trim());
    f.append("budget_s", budget);
    post("/api/jobs", f);
  };

  return (
    <>
      <Card title="Examples">
        <div className="examples">
          {examples.map((e) => (
            <button key={e.name} className="example" onClick={() => post(`/api/examples/${e.name}/run`)}>
              <b>{e.name}</b><span>{e.description}</span>
            </button>
          ))}
        </div>
      </Card>
      <Card title="Analyse your own solution">
        <div className="form">
          <div className="seg">
            <button className={custom ? "" : "on"} onClick={() => setCustom(false)}>Exact match</button>
            <button className={custom ? "on" : ""} onClick={() => setCustom(true)}>Custom checker (testlib)</button>
          </div>
          {fileList.map(([k, label]) => (
            <label key={k} className="file">{label}
              <input type="file" onChange={(e) => setFiles({ ...files, [k]: e.target.files[0] })} />
              {files[k] && <span className={files[k].size > 1 << 20 ? "bad" : "meta"}>{files[k].name} · {kb(files[k].size)}</span>}
            </label>
          ))}
          <label className="file">Generator arguments
            <span className="argrow">
              <input className="text" value={template} onChange={(e) => setTemplate(e.target.value)} spellCheck={false} />
              <select value={PRESETS.includes(template) ? template : ""} onChange={(e) => e.target.value && setTemplate(e.target.value)}>
                <option value="">preset…</option>
                {PRESETS.map((p, i) => <option key={p} value={p}>{PRESET_NAMES[i]}</option>)}
              </select>
            </span>
            {tErr && <span className="bad">{tErr}</span>}
            <span className="meta">{"{seed} and {size} must be whole arguments, e.g. -n {size}, not -n={size}."}</span>
          </label>
          <div className="seg">
            {BUDGETS.map(([b, l]) => <button key={b} className={b === budget ? "on" : ""} onClick={() => setBudget(b)}>{l}</button>)}
          </div>
          <p className="meta">Files must be self-contained. Available headers: testlib.h, random.h, fastio.h.
            If a bug is found, an LLM explanation runs after the budget (~15–30 s).</p>
          {big && <p className="bad">{big[1]} file is larger than 1 MB.</p>}
          {error && <p className="bad">Server: {error}</p>}
          <button className="submit" disabled={!valid} onClick={submit}>Start analysis</button>
        </div>
      </Card>
    </>
  );
}
