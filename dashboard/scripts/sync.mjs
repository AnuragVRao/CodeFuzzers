// Copies ../results/summary.json (or the file named by $SUMMARY) to public/summary.json, which
// the dashboard fetches at runtime. Run by "npm run dev" and "npm run build" before Vite starts.
// A missing summary is not an error: the dashboard then shows "No data yet" everywhere.
import { copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs";

const src = process.env.SUMMARY || "../results/summary.json";
mkdirSync("public", { recursive: true });
if (existsSync(src)) {
  copyFileSync(src, "public/summary.json");
  console.log(`sync: ${src} -> public/summary.json`);
} else {
  rmSync("public/summary.json", { force: true });
  console.log(`sync: ${src} not found; dashboard will show "No data yet"`);
}
