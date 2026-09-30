import assert from "node:assert/strict";
import fs from "node:fs";

const html = fs.readFileSync(new URL("./dist/index.html", import.meta.url), "utf8");
assert.match(html, /AI Outfit Studio/);
const scriptPath = html.match(/src="(\/assets\/[^\"]+\.js)"/)?.[1];
const cssPath = html.match(/href="(\/assets\/[^\"]+\.css)"/)?.[1];
assert.ok(scriptPath, "Vite JavaScript asset is referenced by index.html");
assert.ok(cssPath, "Vite CSS asset is referenced by index.html");
const script = fs.readFileSync(new URL(`.\u002fdist${scriptPath}`, import.meta.url), "utf8");
const css = fs.readFileSync(new URL(`.\u002fdist${cssPath}`, import.meta.url), "utf8");
assert.ok(script.includes("dashboard/summary"));
assert.ok(script.includes("/projects/"));
assert.ok(script.includes("/jobs/"));
assert.ok(script.includes("/backups"));
assert.match(css, /\.app-layout/);
assert.match(css, /\.clothing-slot/);
console.log("static frontend assertions passed");
