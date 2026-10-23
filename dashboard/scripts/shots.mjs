// Captures 1280x720 screenshots of the Analyze tab (and the Bugs tab) into dashboard/shots/ (gitignored).
// Usage: node scripts/shots.mjs   (needs `npm run build`, chromium from `npx playwright install chromium`;
// starts tools/server.py and `vite preview` itself and stops the server for the last "not running" shot)
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const ROOT = fileURLToPath(new URL("../../", import.meta.url)), OUT = fileURLToPath(new URL("../shots/", import.meta.url));
const URL_ = "http://127.0.0.1:4173/";
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const up = async (u) => { try { return (await fetch(u)).ok; } catch { return false; } };
const wait = async (u) => { for (let i = 0; i < 60 && !(await up(u)); i++) await sleep(500); };

const server = spawn("python3", ["tools/server.py"], { cwd: ROOT, stdio: "ignore" });
const preview = spawn("npx", ["vite", "preview", "--host", "127.0.0.1", "--port", "4173"], { cwd: ROOT + "dashboard", stdio: "ignore" });
await Promise.all([wait("http://127.0.0.1:8000/api/examples"), wait(URL_)]);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const shot = (name) => page.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
const openAnalyze = async () => { await page.goto(URL_); await page.getByRole("button", { name: "Analyze" }).click(); };
const run = async (example) => { await page.getByRole("button", { name: new RegExp(example) }).first().click(); };
const finished = () => page.waitForSelector(".banner", { timeout: 200000 });
const back = () => page.getByRole("button", { name: "← back" }).click();

await openAnalyze();
await page.waitForSelector(".example");
await shot("01-form");
await page.locator(".text").fill("-n={size}");
await shot("02-invalid-template");

await run("affine_point_bug");                 // finished bug report with the LLM card
await finished(); await shot("04-bug-report"); await back();
await run("range_min_correct");                // running job mid-hunt, then the clean report
await sleep(20000); await shot("03-running");
await finished(); await shot("05-clean-report"); await back();
await run("broken_compile"); await finished(); await shot("06-failed"); await back();
await run("affine_point_seedonly"); await finished(); await shot("07-seed-only"); await back();
await page.waitForSelector("table"); await shot("08-history");
await page.goto(URL_); await page.getByRole("button", { name: "Bugs" }).click(); await page.getByText("Show failing test").first().click(); await sleep(500); await shot("10-bugs-tab");

server.kill("SIGINT"); await sleep(1500);
await openAnalyze(); await sleep(500); await shot("09-server-down");

await browser.close();
preview.kill();
