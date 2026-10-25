/**
 * Prueft, was auf dem Bildschirm steht -- nicht, was in den Dateien steht.
 *
 *   node tools/check_ui.mjs
 *
 * Warum es das gibt
 * -----------------
 * Die Qualitaetssicherung hat Symbol **und** Textlabel der gruenen Ampel aus
 * app/index.html entfernt -- ein Verstoss gegen Festlegung F1, AK-01.2 und
 * NFR-08 -- und danach meldeten 157 von 158 Pruefungen gruen, und
 * check_app.mjs sagte "Das Cockpit startet sauber."
 *
 * Alle uebrigen Pruefungen sehen Dateien, Zahlen oder Ausnahmen. Keine sieht,
 * was ein Betrachter liest. Genau diese Luecke hat fuenf offene
 * Akzeptanzkriterien unentdeckt gelassen.
 *
 * Dieses Skript faehrt den Browser ueber das DevTools-Protokoll, klickt die
 * echten Bedienelemente und prueft zwanzig harte Aussagen ueber das gerenderte
 * Dokument. Es ist bewusst schmal: Jede Aussage entspricht einem
 * Akzeptanzkriterium, und jede faellt auf, wenn jemand sie bricht.
 */

import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const APP = join(ROOT, "app", "index.html");
const METRICS = join(ROOT, "data", "metrics.json");

const BROWSERS = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
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

const bestanden = [];
const gefallen = [];
const uebersprungen = [];

function pruefe(nummer, kriterium, aussage, bedingung, beobachtet = "") {
  const zeile = `${String(nummer).padStart(2)}. [${kriterium}] ${aussage}`;
  if (bedingung === null) {
    // null heisst "konnte nicht geprueft werden". Das zaehlt ausdruecklich
    // nicht als bestanden -- eine still uebersprungene Pruefung ist genau die
    // Sorte Test, die dieses Werkzeug ersetzen soll.
    uebersprungen.push(`${zeile}\n      Grund: ${beobachtet || "Bedienelement nicht gefunden"}`);
  } else if (bedingung) {
    bestanden.push(zeile);
  } else {
    gefallen.push(`${zeile}\n      beobachtet: ${beobachtet || "Bedingung nicht erfuellt"}`);
  }
}

async function main() {
  if (!existsSync(APP)) { console.log("app/index.html fehlt."); return 0; }
  const browser = BROWSERS.find((path) => existsSync(path));
  if (!browser) { console.error("Kein Chromium gefunden."); return 2; }

  const metrics = JSON.parse(readFileSync(METRICS, "utf8"));
  const port = 9000 + Math.floor(Math.random() * 900);
  const profile = mkdtempSync(join(tmpdir(), "cockpit-ui-"));
  const child = spawn(browser, ["--headless=new", "--disable-gpu", "--no-first-run",
    "--no-default-browser-check", "--window-size=1440,900",
    `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, "about:blank"], { stdio: "ignore" });

  let devtools;
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
    const klick = async (text) => run(`(() => {
      const wanted = ${JSON.stringify("")} || null;
      const ziel = [...document.querySelectorAll('button, a, [role="tab"]')].find((el) => {
        const t = (el.innerText || '').trim();
        return t === ${JSON.stringify(text)} || t.startsWith(${JSON.stringify(text)});
      });
      if (!ziel) return null; ziel.click(); return (ziel.innerText || '').trim();
    })()`);
    const klickId = async (id) => run(`(() => { const b = document.getElementById(${JSON.stringify(id)});
      if (!b || b.disabled) return null; b.click(); return true; })()`);

    // ---- Kopfbereich und Grundaufbau ----------------------------------- //
    const kopf = await run("document.querySelector('.kopf')?.innerText ?? ''");
    pruefe(1, "Regel 3", "Hinweiszeile steht im Kopfbereich",
      kopf.includes("Demo mit fiktiven Daten") && kopf.includes("erstellt mit KI-Unterstützung"), kopf.slice(0, 90));

    const reiter = await run("[...document.querySelectorAll('[data-modul]')].map(b => b.innerText.trim())");
    pruefe(2, "SPEC 4.4", "Sieben Module in der Navigation",
      Array.isArray(reiter) && reiter.length === 7, JSON.stringify(reiter));

    // ---- Ampeln: Farbe UND Symbol UND Text (F1, NFR-08) ---------------- //
    const ampeln = await run(`[...document.querySelectorAll('.ampel')].map(a => ({
      text: (a.innerText || '').trim(),
      zeichen: (a.querySelector('.zeichen')?.innerText || '').trim(),
      klasse: a.className
    }))`);
    const ohneText = (ampeln || []).filter((a) => !a.text || a.text.replace(a.zeichen, "").trim().length < 3);
    pruefe(3, "F1/NFR-08", "Jede Ampel traegt ein Textlabel",
      (ampeln || []).length > 0 && ohneText.length === 0,
      `${(ampeln || []).length} Ampeln, davon ${ohneText.length} ohne Text`);
    const ohneZeichen = (ampeln || []).filter((a) => !a.zeichen);
    pruefe(4, "F1/NFR-08", "Jede Ampel traegt ein Symbol",
      (ampeln || []).length > 0 && ohneZeichen.length === 0,
      `${ohneZeichen.length} Ampeln ohne Symbol`);
    const ohneKlasse = (ampeln || []).filter((a) => !/ampel-(green|yellow|red|grey)/.test(a.klasse));
    pruefe(5, "F1", "Jede Ampel traegt eine Statusfarbe",
      ohneKlasse.length === 0, `${ohneKlasse.length} Ampeln ohne Statusklasse`);

    // ---- Kacheln: Reihenfolge und Inhalt (AK-01.1, AK-01.2) ------------ //
    const kachelNamen = await run("[...document.querySelectorAll('.kpi-name')].map(e => e.innerText.trim())");
    pruefe(6, "AK-01.1", "Zehn Pflichtkennzahlen als Kacheln",
      (kachelNamen || []).length === 10, `${(kachelNamen || []).length} Kacheln`);
    pruefe(7, "AK-01.1", "Angebotsdurchlaufzeit steht an erster Stelle, Aktivitaetsgrad an letzter",
      (kachelNamen || [])[0]?.startsWith("Angebotsdurchlaufzeit") &&
      (kachelNamen || [])[9]?.startsWith("Aktivitätsgrad"),
      `erste: ${(kachelNamen || [])[0]}, letzte: ${(kachelNamen || [])[9]}`);

    const kachelTexte = await run("[...document.querySelectorAll('.kpi')].map(e => e.innerText)");
    const ohneZiel = (kachelTexte || []).filter((t) => !t.includes("Ziel"));
    pruefe(8, "AK-01.2", "Jede Kachel nennt ihren Zielwert",
      ohneZiel.length === 0, `${ohneZiel.length} Kacheln ohne Zielangabe`);

    // Die Reklamationsquote ist der Fall, an dem die Stellenzahl haengt.
    const reklamation = (kachelTexte || []).find((t) => t.startsWith("Reklamationsquote")) ?? "";
    const erwartet = metrics.kpis.complaint_rate_lines.text.replace(/\s/g, " ");
    pruefe(9, "R5/A12", "Reklamationsquote zeigt zwei Nachkommastellen",
      reklamation.replace(/\s/g, " ").includes(erwartet), reklamation.split("\n").slice(0, 3).join(" | "));

    // ---- Filter wirken (AK-02.2) --------------------------------------- //
    const vorher = (kachelTexte || []).find((t) => t.startsWith("Angebotserfolgsquote")) ?? "";
    await run(`(() => { const s = [...document.querySelectorAll('select,button')]
      .find(e => (e.innerText||e.getAttribute('aria-label')||'').includes('Markt')); if (s) s.click(); })()`);
    await sleep(400);
    const atGesetzt = await run(`(() => {
      const ziel = [...document.querySelectorAll('button,label,option')]
        .find(e => (e.innerText || e.value || '').trim() === 'Schweden');
      if (!ziel) return null; ziel.click(); return true; })()`);
    await sleep(900);
    const nachher = await run(`[...document.querySelectorAll('.kpi')].map(e => e.innerText)
      .find(t => t.startsWith('Angebotserfolgsquote')) ?? ''`);
    pruefe(10, "AK-02.2", "Filter Markt=SE aendert die Kennzahl",
      atGesetzt ? vorher !== nachher : null,
      atGesetzt ? `vorher/nachher gleich: ${vorher.split("\n")[1]}` : "Filterknopf nicht gefunden -- uebersprungen");

    const filterzeile = await run("document.querySelector('.filterzeile, .aktive-filter, main p')?.innerText ?? ''");
    pruefe(11, "AK-02.2", "Die aktive Filterkombination steht als Text ueber dem Inhalt",
      filterzeile.includes("Markt"), filterzeile.slice(0, 80));

    await run(`(() => { const b = [...document.querySelectorAll('button')]
      .find(e => e.innerText.trim().startsWith('Filter zurücksetzen')); if (b) b.click(); })()`);
    await sleep(700);

    // ---- Angebotskapazitaet je Vertriebspartner (AK-06.4) --------------- //
    await klick("Partner-Scorecard");
    await sleep(1000);
    const scorecard = await run("document.querySelector('main')?.innerText ?? ''");
    const kapazitaetstelle = scorecard.indexOf("Angebotskapazität im Wochenverlauf");
    console.log(`  (Beleg zu 12) Kapazitaetsbereich: ${
      kapazitaetstelle < 0
        ? "(kein Abschnitt zur Angebotskapazitaet im Modul)"
        : scorecard.slice(kapazitaetstelle, kapazitaetstelle + 180).replace(/\n/g, " | ")}`);

    // AK-06.4 meint den Kapazitaetsverlauf, nicht die Tabelle: Unter der Kurve
    // muss die Zahl der Engpasswochen je Partner stehen, und die Vertretung in
    // NO -- der Wachstumsengpass des Datensatzes -- muss dort Engpasswochen haben.
    const engpasszeile = scorecard.split("\n")
      .find((zeile) => zeile.startsWith("Wochen über der Engpassschwelle:")) ?? "";
    pruefe(12, "AK-06.4", "Kapazitaetsverlauf nennt die Engpasswochen je Vertriebspartner",
      kapazitaetstelle >= 0 && /Vertretung 5 \(NO, DK\) [1-9]/.test(engpasszeile),
      engpasszeile || "Zeile 'Wochen über der Engpassschwelle:' fehlt");

    // ---- Auffaelligkeiten: Kennzeichnung und Fachbereiche --------------- //
    await klick("Auffälligkeiten");
    await sleep(1000);
    const befunde = await run("document.querySelector('main')?.innerText ?? ''");
    pruefe(13, "F5/AK-07.3", "Erzeugte Texte sind als automatisch erstellt gekennzeichnet",
      befunde.includes("automatisch erstellt"), befunde.slice(0, 80));
    pruefe(14, "AK-09.3", "Folgeeffekt nennt ausdruecklich keinen Ursachennachweis",
      befunde.includes("kein statistischer Ursachennachweis"), "Satz nicht gefunden");
    const karten = await run("document.querySelectorAll('.befund, .befundkarte, article').length");
    pruefe(15, "AK-07.2", "Mindestens fuenf Befunde in der Liste",
      (karten ?? 0) >= 5, `${karten} Karten gefunden`);
    pruefe(16, "SPEC 3.4", "Die Zahl unbewerteter Zeitreihen wird ausgewiesen",
      /Zeitreihen? blieb/.test(befunde), "Hinweis auf unbewertete Zeitreihen fehlt");

    // ---- Demo-Fall (AK-18.1 bis AK-18.4) -------------------------------- //
    await klick("Übersicht");
    await sleep(600);
    const start = await klickId("demo-start");
    await sleep(1100);
    let zaehler = await run("document.body.innerText.match(/Schritt\\s+1\\s+von\\s+6/)?.[0] ?? ''");
    pruefe(17, "AK-18.1", "Demo-Fall beginnt bei Schritt 1 von 6",
      Boolean(start) && zaehler.length > 0, zaehler || "Schrittzaehler nicht gefunden");

    let alleSchritte = true;
    for (let schritt = 2; schritt <= 6; schritt += 1) {
      await klickId("demo-weiter");
      await sleep(900);
      const jetzt = await run(`document.body.innerText.match(/Schritt\\s+${schritt}\\s+von\\s+6/)?.[0] ?? ''`);
      if (!jetzt) { alleSchritte = false; break; }
    }
    pruefe(18, "AK-18.2", "Alle sechs Schritte lassen sich durchschalten",
      alleSchritte, "Ablauf blieb vor Schritt 6 stehen");

    const letzterSchritt = await run("document.querySelector('main')?.innerText ?? ''");
    pruefe(19, "AK-18.6", "Schritt 6 zeigt den Management-Report",
      letzterSchritt.includes("Management-Report") || letzterSchritt.includes("Lagebericht"),
      letzterSchritt.slice(0, 80).replace(/\n/g, " | "));

    await run("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))");
    await sleep(700);
    const nachEscape = await run("document.body.innerText.includes('Schritt') && /Schritt\\s+\\d+\\s+von\\s+6/.test(document.body.innerText)");
    pruefe(20, "AK-18.3", "Escape beendet den Demo-Fall",
      nachEscape === false, "Schrittanzeige nach Escape noch sichtbar");

  } catch (problem) {
    gefallen.push(`Abbruch: ${problem.message ?? problem}`);
  } finally {
    devtools?.close();
    child.kill();
    await sleep(400);
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* Browser haelt es noch */ }
  }

  console.log(
    `Oberflaechenpruefung: ${bestanden.length} bestanden, ${gefallen.length} gefallen, `
    + `${uebersprungen.length} uebersprungen\n`
  );
  for (const zeile of bestanden) console.log(`  ok   ${zeile}`);
  if (uebersprungen.length) {
    console.log();
    for (const zeile of uebersprungen) console.log(`  ??   ${zeile}`);
  }
  if (gefallen.length) {
    console.log();
    for (const zeile of gefallen) console.log(`  FEHL ${zeile}`);
  }
  // Uebersprungenes ist kein Fehlschlag, aber auch kein Erfolg: Rueckgabewert 2
  // macht sichtbar, dass nicht alles geprueft werden konnte.
  if (gefallen.length) return 1;
  if (uebersprungen.length) return 2;
  return 0;
}

process.exit(await main());
