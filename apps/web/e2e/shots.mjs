import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const OUT = "../../artifacts/shots";
mkdirSync(OUT, { recursive: true });
const BASE = process.env.BASE || "http://localhost:3000";
const API = process.env.API || "http://localhost:8000";

const shots = [
  ["intelligence", "/"],
  ["events", "/events"],
  ["discovery", "/discovery"],
  ["lp", "/lp"],
  ["talent", "/talent"],
  ["network", "/network"],
  ["models", "/models"],
  ["data-quality", "/data-quality"],
  ["weekly-runs", "/weekly-runs"],
];

const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1440, height: 1000 }, colorScheme: "dark" });

// person page: resolve Sarah's id
const res = await fetch(`${API}/people?q=Sarah%20Chen`);
const sid = (await res.json()).items[0].id;

for (const [name, path] of shots) {
  await page.goto(BASE + path, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
  console.log("shot", name);
}

await page.goto(`${BASE}/person/${sid}`, { waitUntil: "networkidle" });
await page.waitForTimeout(800);
await page.screenshot({ path: `${OUT}/person-top.png`, fullPage: false });
// expand the timing dimension for the decomposition shot
await page.evaluate(() => document.querySelectorAll("details").forEach((d) => (d.open = true)));
await page.waitForTimeout(300);
await page.screenshot({ path: `${OUT}/person-full.png`, fullPage: true });
console.log("shot person");

await b.close();
