/**
 * Smoke test for the cockpit in a real browser -- no dependency beyond Node and Chrome.
 *
 *   node tools/check_app.mjs                      status, console errors, timing
 *   node tools/check_app.mjs --offline            same, with the network cut (NFR-03)
 *   node tools/check_app.mjs --screenshot <pfad>  additionally save a screenshot
 *
 * Why the DevTools protocol and not `--dump-dom`
 * ----------------------------------------------
 * On Windows chrome.exe is a GUI binary: its standard output never reaches a pipe,
 * so `--dump-dom` silently returns nothing. Driving the browser over the DevTools
 * protocol works, and it gives us the thing that actually matters -- the real
 * console output and every uncaught exception, which is what a blank cockpit in
 * the interview would look like from the inside.
 *
 * Node 22 ships a global WebSocket, so this needs no packages at all.
 *
 * What a passing run proves
 * -------------------------
 *   - the page loads from file:// (NFR-01, opened by double click)
 *   - no uncaught exception, no console error
 *   - the app reports data-cockpit-status="ready" (decision A14)
 *   - the disclosure line and the demo button are in the rendered page
 *   - with --offline: the cockpit still comes up and replaces diagrams with
 *     labelled value tables (NFR-03)
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

const args = process.argv.slice(2);
const OFFLINE = args.includes("--offline");
const SCREENSHOT = args.includes("--screenshot")
  ? args[args.indexOf("--screenshot") + 1]
  : null;

function findBrowser() {
  const found = BROWSERS.find((path) => existsSync(path));
  if (!found) {
    console.error(
      "Kein Chromium-Browser gefunden. Chrome oder Edge installieren, " +
        "oder den Pfad in tools/check_app.mjs ergaenzen."
    );
    process.exit(2);
  }
  return found;
}

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

async function waitForEndpoint(port, attempts = 60) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) return await response.json();
    } catch {
      /* browser not up yet */
    }
    await sleep(250);
  }
  throw new Error("Der Browser hat die DevTools-Schnittstelle nicht geoeffnet.");
}

/** Minimal DevTools client: send a command, await its reply, observe events. */
class Devtools {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = [];
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve: settle, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        message.error ? reject(new Error(message.error.message)) : settle(message.result);
      } else if (message.method) {
        for (const listener of this.listeners) listener(message);
      }
    });
  }

  static async connect(url) {
    const socket = new WebSocket(url);
    await new Promise((settle, reject) => {
      socket.addEventListener("open", settle, { once: true });
      socket.addEventListener("error", () => reject(new Error("WebSocket-Verbindung fehlgeschlagen")), { once: true });
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

  on(listener) {
    this.listeners.push(listener);
  }

  close() {
    this.socket.close();
  }
}

async function main() {
  if (!existsSync(APP)) {
    console.log("app/index.html existiert noch nicht -- nichts zu pruefen.");
    return 0;
  }

  const browser = findBrowser();
  const port = 9000 + Math.floor(Math.random() * 900);
  const profile = mkdtempSync(join(tmpdir(), "cockpit-check-"));

  const child = spawn(
    browser,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--window-size=1440,900",
      `--user-data-dir=${profile}`,
      `--remote-debugging-port=${port}`,
      "about:blank",
    ],
    { stdio: "ignore", detached: false }
  );

  const problems = [];
  const consoleErrors = [];
  const failedRequests = [];
  let devtools;

  try {
    const version = await waitForEndpoint(port);
    console.log(`Browser:  ${version.Browser}`);
    console.log(`Seite:    app/index.html`);

    const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    const page = targets.find((target) => target.type === "page");
    if (!page) throw new Error("Kein Seiten-Ziel im Browser gefunden.");

    devtools = await Devtools.connect(page.webSocketDebuggerUrl);

    devtools.on((message) => {
      if (message.method === "Runtime.exceptionThrown") {
        const details = message.params.exceptionDetails;
        consoleErrors.push(
          `Ausnahme: ${details.exception?.description ?? details.text}`
        );
      }
      if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
        const text = message.params.args
          .map((arg) => arg.value ?? arg.description ?? "")
          .join(" ");
        consoleErrors.push(`console.error: ${text}`);
      }
      if (message.method === "Log.entryAdded" && message.params.entry.level === "error") {
        const entry = message.params.entry;
        // A blocked external resource is expected in offline mode.
        if (entry.source === "network") failedRequests.push(entry.text);
        else consoleErrors.push(`${entry.source}: ${entry.text}`);
      }
    });

    await devtools.send("Runtime.enable");
    await devtools.send("Log.enable");
    await devtools.send("Page.enable");
    await devtools.send("Network.enable");

    if (OFFLINE) {
      console.log("Modus:    ohne Netz (NFR-03)");
      await devtools.send("Network.emulateNetworkConditions", {
        offline: true,
        latency: 0,
        downloadThroughput: 0,
        uploadThroughput: 0,
      });
    }

    const loaded = new Promise((settle) => {
      devtools.on((message) => {
        if (message.method === "Page.loadEventFired") settle();
      });
    });

    const started = Date.now();
    await devtools.send("Page.navigate", { url: pathToFileURL(APP).href });
    await Promise.race([loaded, sleep(20000)]);
    const loadMs = Date.now() - started;

    // Give the cockpit a moment to render after load, then read its own verdict.
    await sleep(1500);

    const evaluate = async (expression) => {
      const result = await devtools.send("Runtime.evaluate", {
        expression,
        returnByValue: true,
      });
      return result.result?.value;
    };

    const status = await evaluate("document.documentElement.dataset.cockpitStatus ?? null");
    const error = await evaluate("document.documentElement.dataset.cockpitError ?? null");
    const text = await evaluate("document.body.innerText");
    const chartLibrary = await evaluate("typeof Chart !== 'undefined'");

    console.log(`Status:   ${status ?? "nicht gesetzt"}`);
    console.log(`Ladezeit: ${loadMs} ms (Grenze 2000 ms, NFR-04)`);
    console.log(`Diagrammbibliothek geladen: ${chartLibrary ? "ja" : "nein"}`);

    if (status === null) {
      problems.push(
        "Das Attribut data-cockpit-status fehlt. Die App muss nach der Initialisierung " +
          '"ready" setzen (Entscheidung A14).'
      );
    } else if (status !== "ready") {
      problems.push(`Die App meldet den Status "${status}" statt "ready".`);
    }
    if (error) problems.push(`Die App meldet einen Fehler: ${error}`);
    if (loadMs > 2000) problems.push(`Ladezeit ${loadMs} ms ueberschreitet die Grenze von 2000 ms.`);

    for (const marker of ["Demo mit fiktiven Daten", "Demo-Fall starten"]) {
      if (!String(text ?? "").includes(marker)) {
        problems.push(`Der Text "${marker}" fehlt auf der gerenderten Seite.`);
      }
    }

    if (OFFLINE) {
      if (chartLibrary) {
        problems.push("Im Offline-Modus wurde die Diagrammbibliothek trotzdem geladen -- Test ungueltig.");
      }
      const hasFallback = String(text ?? "").includes("Wertetabelle") ||
        String(text ?? "").includes("Diagramm nicht verfuegbar") ||
        String(text ?? "").includes("Diagramm nicht verfügbar");
      if (!hasFallback) {
        problems.push(
          "Ohne Netz ist keine Ersatzdarstellung zu finden. NFR-03 verlangt an Stelle " +
            "jedes Diagramms eine beschriftete Wertetabelle."
        );
      }
    }

    for (const message of consoleErrors) problems.push(`Konsole: ${message}`);

    if (SCREENSHOT) {
      const shot = await devtools.send("Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: true,
      });
      writeFileSync(SCREENSHOT, Buffer.from(shot.data, "base64"));
      console.log(`Screenshot: ${SCREENSHOT}`);
    }

    if (failedRequests.length && !OFFLINE) {
      console.log(`Hinweis:  ${failedRequests.length} externe Anfrage(n) fehlgeschlagen:`);
      for (const request of failedRequests.slice(0, 5)) console.log(`          ${request}`);
    }
  } catch (problem) {
    problems.push(String(problem.message ?? problem));
  } finally {
    devtools?.close();
    child.kill();
    await sleep(500);
    try {
      rmSync(profile, { recursive: true, force: true });
    } catch {
      /* the browser may still hold the profile; it is in the temp directory */
    }
  }

  console.log();
  if (problems.length) {
    console.log(`${problems.length} Problem(e):`);
    for (const problem of problems) console.log(`  - ${problem}`);
    return 1;
  }
  console.log("Das Cockpit startet sauber.");
  return 0;
}

process.exit(await main());
