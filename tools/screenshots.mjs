/**
 * Screenshot je Modul -- fuer die Sichtpruefung durch den Program Lead und fuer QA.
 *
 *   node tools/screenshots.mjs <zielordner>
 *
 * Klickt die sieben Reiter der Reihe nach an und legt je einen Screenshot ab.
 * Danach noch einmal dasselbe mit gesetztem Filter Markt = SE, weil der Demo-Fall
 * dort spielt und die Randfaelle erst mit Filter sichtbar werden.
 *
 * Wie check_app.mjs faehrt das Skript den Browser ueber das DevTools-Protokoll
 * und klickt die echten Bedienelemente -- ein Reiter, der nicht mehr reagiert,
 * faellt damit auf, statt uebergangen zu werden.
 */

import { spawn } from "node:child_process";
import { existsSync, writeFileSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const APP = join(ROOT, "app", "index.html");
const TARGET = process.argv[2];

if (!TARGET) {
  console.error("Aufruf: node tools/screenshots.mjs <zielordner>");
  process.exit(2);
}

const BROWSERS = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
];

const MODULE = [
  "Übersicht", "Vertriebsprozess", "Partner-Scorecard", "Auffälligkeiten",
  "Maßnahmen", "Wachstumsszenario", "Report & Vorlage",
];

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

class Devtools {
  constructor(socket) {
    this.socket = socket; this.nextId = 1; this.pending = new Map();
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve: settle, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        message.error ? reject(new Error(message.error.message)) : settle(message.result);
      }
    });
  }
  static async connect(url) {
    const socket = new WebSocket(url);
    await new Promise((settle, reject) => {
      socket.addEventListener("open", settle, { once: true });
      socket.addEventListener("error", () => reject(new Error("WebSocket fehlgeschlagen")), { once: true });
    });
    return new Devtools(socket);
  }
  send(method, params = {}) {
    const id = this.nextId++;
    this.socket.send(JSON.stringify({ id, method, params }));
    return new Promise((settle, reject) => {
      this.pending.set(id, { resolve: settle, reject });
      setTimeout(() => { if (this.pending.delete(id)) reject(new Error(`Zeitueberschreitung ${method}`)); }, 30000);
    });
  }
  close() { this.socket.close(); }
}

const CLICK = (label) => `(() => {
  const wanted = ${JSON.stringify(label)}.toLowerCase();
  const hit = [...document.querySelectorAll('button, a, [role="tab"]')].find((element) => {
    const text = (element.innerText || '').trim().toLowerCase();
    return text === wanted || text.startsWith(wanted);
  });
  if (!hit) return null;
  hit.click();
  return (hit.innerText || '').trim();
})()`;

async function main() {
  if (!existsSync(APP)) { console.log("app/index.html fehlt."); return 0; }
  const browser = BROWSERS.find((path) => existsSync(path));
  if (!browser) { console.error("Kein Chromium gefunden."); return 2; }
  mkdirSync(TARGET, { recursive: true });

  const port = 9000 + Math.floor(Math.random() * 900);
  const profile = mkdtempSync(join(tmpdir(), "cockpit-shots-"));
  const child = spawn(browser, ["--headless=new", "--disable-gpu", "--no-first-run",
    "--no-default-browser-check", "--window-size=1440,900",
    `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, "about:blank"], { stdio: "ignore" });

  let devtools;
  const fehlend = [];
  try {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      try { if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) break; } catch { /* warten */ }
      await sleep(250);
    }
    const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    devtools = await Devtools.connect(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
    await devtools.send("Page.enable");
    await devtools.send("Runtime.enable");
    await devtools.send("Page.navigate", { url: pathToFileURL(APP).href });
    await sleep(2500);

    const run = async (expression) =>
      (await devtools.send("Runtime.evaluate", { expression, returnByValue: true })).result?.value;

    const shoot = async (name) => {
      const shot = await devtools.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
      const file = join(TARGET, `${name}.png`);
      writeFileSync(file, Buffer.from(shot.data, "base64"));
      return file;
    };

    for (const [index, name] of MODULE.entries()) {
      const clicked = await run(CLICK(name));
      if (!clicked) { fehlend.push(name); continue; }
      await sleep(1100);
      const file = await shoot(`${index + 1}-${name.replace(/[^\wÄÖÜäöüß]+/g, "-")}`);
      const ueberschrift = await run("document.querySelector('main h1, main h2')?.innerText ?? ''");
      console.log(`${index + 1}. ${clicked.padEnd(20)} -> ${file.split("\\").pop()}   Ueberschrift: "${ueberschrift}"`);
    }

    // Demo-Fall: Schritt fuer Schritt festhalten. Geklickt wird ueber die
    // Element-Kennung, nicht ueber den Text -- die Demoleiste liegt fest am
    // unteren Rand, und ein Textklick trifft dort leicht den falschen Knopf.
    await run(CLICK("Übersicht"));
    await sleep(600);
    const start = await run("(() => { const b = document.getElementById('demo-start'); if (!b) return null; b.click(); return true; })()");
    if (!start) {
      fehlend.push("Demo-Fall starten");
    } else {
      for (let schritt = 1; schritt <= 6; schritt += 1) {
        await sleep(1100);
        await shoot(`demo-${schritt}`);
        const zaehler = await run("document.body.innerText.match(/Schritt\\s+\\d+\\s+von\\s+6/)?.[0] ?? ''");
        const modul = await run("document.querySelector('main h1, main h2')?.innerText ?? ''");
        console.log(`Demo ${schritt}: ${zaehler || "kein Schrittzaehler"}   Modul: "${modul}"`);
        if (zaehler && !zaehler.includes(`Schritt ${schritt} `)) {
          fehlend.push(`Demo-Schritt ${schritt} (Anzeige: ${zaehler})`);
        }
        if (schritt < 6) {
          const weiter = await run("(() => { const b = document.getElementById('demo-weiter'); if (!b || b.disabled) return null; b.click(); return true; })()");
          if (!weiter) fehlend.push(`Knopf 'weiter' bei Schritt ${schritt}`);
        }
      }
    }
  } catch (problem) {
    console.error("Fehler:", problem.message ?? problem);
    return 1;
  } finally {
    devtools?.close();
    child.kill();
    await sleep(400);
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* Browser haelt es noch */ }
  }

  if (fehlend.length) {
    console.log(`\nNicht gefunden: ${fehlend.join(", ")}`);
    return 1;
  }
  console.log(`\nAlle Screenshots in ${TARGET}`);
  return 0;
}

process.exit(await main());
