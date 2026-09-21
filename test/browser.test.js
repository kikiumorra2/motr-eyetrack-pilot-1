// Real-browser check of the DOM side (measure.js / dom.js) in headless Chrome via the
// DevTools protocol — no dependencies (Node's built-in WebSocket + a tiny static server).
// Skipped when no Chrome/Chromium binary is found.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { spawn, execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { prng } from "./helpers.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TEXT = "The reporter that attacked the senator admitted the error, and the editor who had assigned the story quietly resigned from the paper the following week.";

function findChrome() {
  const candidates = [
    process.env.MOTR_CHROME,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
  ].filter(Boolean);
  for (const c of candidates) {
    if (c.includes("/")) { if (fs.existsSync(c)) return c; continue; }
    try { return execSync(`command -v ${c}`, { stdio: ["ignore", "pipe", "ignore"] }).toString().trim() || null; } catch { /* next */ }
  }
  return null;
}

const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json", ".css": "text/css" };

function staticServer() {
  const server = http.createServer((req, res) => {
    const file = path.join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port })));
}

async function launchChrome(chrome) {
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), "motr-chrome-"));
  const proc = spawn(chrome, [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
    "--remote-debugging-port=0", `--user-data-dir=${userDir}`, "--window-size=1280,900", "about:blank",
  ], { stdio: ["ignore", "pipe", "pipe"] });
  const port = await new Promise((resolve, reject) => {
    let buf = "";
    const timer = setTimeout(() => reject(new Error("Chrome did not start: " + buf)), 20000);
    proc.stderr.on("data", (d) => {
      buf += d;
      const m = /DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)\//.exec(buf);
      if (m) { clearTimeout(timer); resolve(Number(m[1])); }
    });
    proc.on("exit", (code) => { clearTimeout(timer); reject(new Error(`Chrome exited (${code}): ${buf}`)); });
  });
  const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  const page = targets.find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let id = 0;
  const pending = new Map();
  const listeners = new Map();
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method && listeners.has(msg.method)) listeners.get(msg.method)(msg.params);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    pending.set(++id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error("page error: " + JSON.stringify(r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    return r.result.value;
  };
  const close = async () => {
    try { ws.close(); } catch { /* ignore */ }
    const exited = new Promise((resolve) => { proc.once("exit", resolve); setTimeout(resolve, 3000); });
    try { proc.kill(); } catch { /* ignore */ }
    await exited;
    for (let i = 0; i < 5; i++) {
      try { fs.rmSync(userDir, { recursive: true, force: true }); break; } catch { await new Promise((r) => setTimeout(r, 200)); }
    }
  };
  return { send, evaluate, close, on: (m, f) => listeners.set(m, f) };
}

const chrome = findChrome();

test("headless Chrome: measure.js / dom.js against the real layout engine", { skip: chrome ? false : "no Chrome/Chromium found (set MOTR_CHROME)", timeout: 120000 }, async (t) => {
  const { server, port } = await staticServer();
  let cdp = null;
  try {
    cdp = await launchChrome(chrome);
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 820, height: 800, deviceScaleFactor: 1, mobile: false });
    const loaded = new Promise((resolve) => cdp.on("Page.loadEventFired", resolve));
    await cdp.send("Page.navigate", { url: `http://127.0.0.1:${port}/test/browser/harness.html` });
    await loaded;
    for (let i = 0; i < 50 && !(await cdp.evaluate("!!window.motrReady")); i++) await new Promise((r) => setTimeout(r, 100));
    assert.ok(await cdp.evaluate("!!window.motrReady"), "harness did not initialise (module import failed?)");

    // 1. measurement of a wrapped sentence
    const words = await cdp.evaluate(`window.words = window.motr.setText(${JSON.stringify(TEXT)})`);
    await cdp.evaluate("new Promise(r => requestAnimationFrame(() => r()))");
    const table = await cdp.evaluate("window.table = window.motr.measure(window.words)");
    await cdp.evaluate("new Promise(r => requestAnimationFrame(() => r()))");
    assert.equal(table.words.length, words.length);
    const lines = new Set(table.words.flatMap((w) => w.frags.map((f) => f.top)));
    assert.ok(lines.size >= 2, `expected the sentence to wrap to >= 2 lines, got ${lines.size}`);
    let trailingSpaces = 0, leadingZero = 0;
    table.words.forEach((w, i) => {
      assert.ok(w.frags.length >= 1, `word ${i} has no fragment`);
      const len = Array.from(words[i]).length;
      for (const f of w.frags) {
        for (let j = 1; j < f.xs.length; j++) assert.ok(f.xs[j] > f.xs[j - 1], `word ${i}: x boundaries not increasing`);
        assert.ok(f.bottom > f.top && f.bottom - f.top < 40, `word ${i}: glyph band ${f.top}-${f.bottom}`);
        if (f.k0 === 0) leadingZero++;
        if (f.k0 + f.xs.length - 2 === len + 1) trailingSpaces++;
      }
      const covered = new Set(w.frags.flatMap((f) => Array.from({ length: f.xs.length - 1 }, (_, j) => f.k0 + j)));
      for (let k = 1; k <= len; k++) assert.ok(covered.has(k), `word ${i} (${words[i]}): character ${k} has no box`);
    });
    assert.equal(leadingZero, 0, "leading spaces should collapse to zero width");
    assert.ok(trailingSpaces >= words.length - lines.size, `trailing spaces measured for ${trailingSpaces}/${words.length} words`);
    t.diagnostic(`layout: ${words.length} words on ${lines.size} lines, ${trailingSpaces} trailing spaces, block ${JSON.stringify(table.block.map(Math.round))}`);

    // 2. legacy elementFromPoint hit test vs hitState. Real mice report integer clientX/Y
    //    (half-integers at DPR 2), so those are asserted; arbitrary fractions are reported.
    const rnd = prng(99);
    const [l, tp, r, b] = table.block;
    const sample = (n, q) => Array.from({ length: n }, () => [q(l - 20 + rnd() * (r - l + 40)), q(tp - 20 + rnd() * (b - tp + 40))]);
    const intPts = sample(8000, Math.round);
    const halfPts = sample(3000, (v) => Math.round(v * 2) / 2);
    const fracPts = sample(3000, (v) => Math.round(v * 10) / 10);
    for (const w of table.words) for (const f of w.frags) for (const x of f.xs) for (const dx of [-1, 0, 1]) for (const dy of [-1, 0, 1]) intPts.push([Math.round(x) + dx, Math.round(f.top) + dy], [Math.round(x) + dx, Math.round(f.bottom) + dy]);
    const results = {};
    const now = await cdp.evaluate("({ block: window.motr.blockRect(), w3: [...document.querySelectorAll('span[data-index]')][3].getBoundingClientRect().toJSON(), scroll: [window.scrollX, window.scrollY], vv: [visualViewport.offsetLeft, visualViewport.offsetTop, visualViewport.scale], inner: [innerWidth, innerHeight] })");
    t.diagnostic(`at compare time: block ${JSON.stringify(now.block)} (measured ${JSON.stringify(table.block)}), word3 top/left ${now.w3.top}/${now.w3.left} (measured ${table.words[3].rect[1]}/${table.words[3].rect[0]}), scroll ${now.scroll}, vv ${now.vv}, inner ${now.inner}`);
    for (const [name, pts] of [["integer", intPts], ["half", halfPts], ["tenth", fracPts]]) {
      const cmp = await cdp.evaluate(`window.motr.compare(window.words, window.table, ${JSON.stringify(pts)})`);
      results[name] = cmp;
      t.diagnostic(`hit-test agreement (${name} coordinates): ${cmp.agree}/${cmp.n} (${(100 * cmp.agree / cmp.n).toFixed(2)}%)` + (cmp.mismatches.length ? " e.g. " + JSON.stringify(cmp.mismatches.slice(0, 4)) : ""));
    }
    assert.ok(results.integer.agree === results.integer.n, `integer-coordinate mismatches: ${JSON.stringify(results.integer.mismatches)}`);
    assert.ok(results.half.agree / results.half.n >= 0.999, `half-pixel mismatches: ${JSON.stringify(results.half.mismatches)}`);
    assert.ok(results.tenth.agree / results.tenth.n >= 0.99, `sub-pixel mismatches: ${JSON.stringify(results.tenth.mismatches)}`);

    // 3. real pointer moves through attachRecorder: sweep the first line, then leave
    await cdp.evaluate("window.motr.startRecorder(window.words, { recordRawTrace: true })");
    const line1 = table.words.filter((w) => w.frags[0].top === Math.min(...lines));
    const y = line1[0].frags[0].top + 8;
    const x0 = line1[0].frags[0].xs[0] - 15, x1 = Math.max(...line1.map((w) => w.frags[w.frags.length - 1].xs.at(-1))) + 15;
    let moves = 0;
    for (let x = x0; x <= x1; x += 2) { await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y }); moves++; }
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 5, y: 5 }); moves++;     // outside the block
    await cdp.evaluate("new Promise(r => setTimeout(r, 50))");
    // 4. relayout: narrower viewport → re-wrap → new snapshot
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 520, height: 800, deviceScaleFactor: 1, mobile: false });
    await cdp.evaluate("new Promise(r => setTimeout(r, 300))");
    const snaps = await cdp.evaluate("window.motr.snapshotCount()");
    const out = await cdp.evaluate("window.motr.finish()");
    const kinds = out.events.map((e) => e.kind).join("");
    const chars = out.events.filter((e) => e.kind === "c").map((e) => e.num);
    t.diagnostic(`recorder: ${out.events.length} events (${chars.length} char changes), ${out.nTrace} trace samples for ${moves} moves, stats ${out.fields.mtStats}`);
    assert.equal(out.stats.n, moves, "every dispatched move must be fed");
    assert.equal(out.nTrace, moves);
    assert.equal(out.stats.coal, 1, "Chrome exposes getCoalescedEvents");
    assert.ok(out.stats.mindt > 0);
    for (let i = 1; i < chars.length; i++) assert.ok(chars[i] > chars[i - 1], `sweep must visit characters left to right: ${chars.join(",")}`);
    const lastWordOnLine1 = table.words.indexOf(line1[line1.length - 1]);
    assert.ok(chars.length >= lastWordOnLine1 + 1, "at least one character per word on the first line");
    assert.match(kinds, /^n?c+n?o/, `expected NONE?, chars..., NONE?, OUT: ${kinds}`);
    assert.equal(snaps, 2, "the viewport change must add one layout snapshot");
    assert.ok(kinds.includes("l"), `relayout token missing: ${kinds}`);
    assert.equal(kinds.at(-1), "e");
    assert.ok(out.rows > chars.length, "expanded legacy rows include the end marker");
    assert.equal(out.stats.trunc, 0);
    t.diagnostic(`handler max ${out.stats.hmax} us, mindt ${out.stats.mindt} ms, payload ${Object.values(out.fields).reduce((n, v) => n + v.length, 0)} bytes`);
  } finally {
    server.close();
    if (cdp) await cdp.close();
  }
});
