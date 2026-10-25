/**
 * Print-layout check for the cockpit (NFR-09).
 *
 *   node tools/check_print.mjs
 *
 * Why a separate tool
 * -------------------
 * ``tools/pdf.py`` renders a file as it loads. The cockpit always opens on the
 * overview, so that only ever measures the overview. NFR-09 is about two views
 * the user has to navigate to: the management report and the decision paper,
 * each of which must print as exactly one A4 page.
 *
 * This script drives the browser over the DevTools protocol: load the file,
 * click the module tab, switch the inner view, then Page.printToPDF with A4
 * geometry and no browser header or footer -- the same way a person would press
 * Ctrl+P. It reports the page count per view.
 *
 * It clicks the real controls rather than calling internal functions, so a tab
 * that no longer reacts shows up as a failure instead of being bypassed.
 */

import { spawn } from "node:child_process";
import { existsSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const APP = join(ROOT, "app", "index.html");

const BROWSERS = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
];

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

/** Count pages in a PDF: Chromium leaves the page tree readable. */
function pageCount(buffer) {
  const text = buffer.toString("latin1");
  const counts = [...text.matchAll(/\/Count\s+(\d+)/g)].map((m) => Number(m[1]));
  if (counts.length) return Math.max(...counts);
  return [...text.matchAll(/\/Type\s*\/Page[^s]/g)].length;
}

class Devtools {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
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
      setTimeout(() => {
        if (this.pending.delete(id)) reject(new Error(`Zeitueberschreitung bei ${method}`));
      }, 30000);
    });
  }

  close() {
    this.socket.close();
  }
}

/**
 * Click the first element whose visible text contains `label`.
 * Returns what was clicked, or null when nothing matched.
 */
const CLICK_BY_TEXT = (label) => `(() => {
  const wanted = ${JSON.stringify(label)}.toLowerCase();
  const candidates = [...document.querySelectorAll('button, a, [role="tab"], [role="button"]')];
  const hit = candidates.find((element) => {
    const text = (element.innerText || element.textContent || '').trim().toLowerCase();
    return text.includes(wanted) && element.offsetParent !== null;
  });
  if (!hit) return null;
  hit.click();
  return (hit.innerText || hit.textContent || '').trim();
})()`;

async function main() {
  if (!existsSync(APP)) {
    console.log("app/index.html existiert noch nicht -- nichts zu pruefen.");
    return 0;
  }
  const browser = BROWSERS.find((path) => existsSync(path));
  if (!browser) {
    console.error("Kein Chromium-Browser gefunden.");
    return 2;
  }

  const port = 9000 + Math.floor(Math.random() * 900);
  const profile = mkdtempSync(join(tmpdir(), "cockpit-print-"));
  const child = spawn(
    browser,
    ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
     `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, "about:blank"],
    { stdio: "ignore" }
  );

  const problems = [];
  let devtools;

  try {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/json/version`);
        if (response.ok) break;
      } catch { /* not up yet */ }
      await sleep(250);
    }
    const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    const page = targets.find((target) => target.type === "page");
    devtools = await Devtools.connect(page.webSocketDebuggerUrl);
    await devtools.send("Page.enable");
    await devtools.send("Runtime.enable");
    // Deliberately no setEmulatedMedia("print") here. The print stylesheet hides
    // the navigation -- that is what NFR-09 asks for -- so switching media before
    // navigating makes every tab invisible and no click finds anything.
    // Page.printToPDF applies print media on its own when it renders.

    await devtools.send("Page.navigate", { url: pathToFileURL(APP).href });
    await sleep(2500);

    const evaluate = async (expression) => {
      const result = await devtools.send("Runtime.evaluate", { expression, returnByValue: true });
      return result.result?.value;
    };

    const printPdf = async (name) => {
      const pdf = await devtools.send("Page.printToPDF", {
        printBackground: true,
        paperWidth: 8.27,      // A4
        paperHeight: 11.69,
        marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0,
        preferCSSPageSize: true,
      });
      const buffer = Buffer.from(pdf.data, "base64");
      const target = join(tmpdir(), `${name}.pdf`);
      writeFileSync(target, buffer);
      return { pages: pageCount(buffer), kb: buffer.length / 1024, path: target };
    };

    // 1. Navigate to the report module.
    const tab = await evaluate(CLICK_BY_TEXT("Report"));
    if (!tab) {
      problems.push('Kein Navigationsknopf mit "Report" gefunden.');
    } else {
      console.log(`Modul geoeffnet ueber: "${tab}"`);
    }
    await sleep(900);

    // 2. The management report view.
    const reportButton = await evaluate(CLICK_BY_TEXT("Management-Report"));
    await sleep(1200);
    const report = await printPdf("cockpit-report");
    console.log(`Management-Report: ${report.pages} Seite(n), ${report.kb.toFixed(0)} KB` +
      (reportButton ? ` (ueber "${reportButton}")` : " (ohne eigenen Umschalter)"));
    if (report.pages !== 1) {
      problems.push(`Management-Report ergibt ${report.pages} Seiten, NFR-09 verlangt genau 1.`);
    }

    // 3. The decision paper view.
    const decisionButton = await evaluate(CLICK_BY_TEXT("Entscheidungsvorlage"));
    await sleep(1200);
    const decision = await printPdf("cockpit-decision");
    console.log(`Entscheidungsvorlage: ${decision.pages} Seite(n), ${decision.kb.toFixed(0)} KB` +
      (decisionButton ? ` (ueber "${decisionButton}")` : " (kein Umschalter gefunden)"));
    if (!decisionButton) {
      problems.push('Kein Umschalter "Entscheidungsvorlage" gefunden -- Ansicht nicht erreichbar.');
    }
    if (decision.pages !== 1) {
      problems.push(`Entscheidungsvorlage ergibt ${decision.pages} Seiten, NFR-09 verlangt genau 1.`);
    }

    console.log(`\nPDFs zum Ansehen: ${report.path}\n                  ${decision.path}`);
  } catch (problem) {
    problems.push(String(problem.message ?? problem));
  } finally {
    devtools?.close();
    child.kill();
    await sleep(400);
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* browser still holds it */ }
  }

  console.log();
  if (problems.length) {
    console.log(`${problems.length} Problem(e):`);
    for (const problem of problems) console.log(`  - ${problem}`);
    return 1;
  }
  console.log("Drucklayout in Ordnung: beide Ansichten je genau eine A4-Seite.");
  return 0;
}

process.exit(await main());
