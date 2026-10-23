// Top-level component: fetches /summary.json once, shows a tab bar and renders the selected tab.
// Each tab receives the whole summary and handles its own missing sections ("No data yet").
import { useEffect, useState } from "react";
import Overview from "./tabs/Overview.jsx";
import Analyze from "./tabs/Analyze.jsx";
import Scaling from "./tabs/Scaling.jsx";
import Hunt from "./tabs/Hunt.jsx";
import Bugs from "./tabs/Bugs.jsx";
import Shrinking from "./tabs/Shrinking.jsx";
import { NoData } from "./ui.jsx";

const TABS = { Overview, Analyze, Scaling, Hunt, Bugs, Shrinking };

export default function App() {
  const [data, setData] = useState(undefined); // undefined = loading, null = no summary
  const [tab, setTab] = useState("Overview");

  useEffect(() => {
    fetch("/summary.json")
      .then((r) => (r.ok ? r.json() : null))
      .then(setData)
      .catch(() => setData(null));
  }, []);

  const Tab = TABS[tab];
  return (
    <div className="page">
      <header>
        <h1>CodeFuzzers</h1>
        <span className="subtitle">parallel differential fuzzing — results</span>
      </header>
      <nav className="tabs">
        {Object.keys(TABS).map((t) => (
          <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
        ))}
      </nav>
      <main>
        {tab === "Analyze" ? <Analyze /> : data === undefined ? <p>Loading…</p> : data === null ? <NoData /> : <Tab data={data} />}
      </main>
    </div>
  );
}
