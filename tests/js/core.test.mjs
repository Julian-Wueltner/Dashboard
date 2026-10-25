/**
 * Node test for the cockpit's JavaScript calculation core (NFR-13, decision A4).
 *
 * Why this exists
 * ---------------
 * The cockpit recalculates every ratio in the browser while the user filters, and
 * the case study prints numbers that Python computed. If the two implementations
 * of the same formula drift apart, the tool and the report contradict each other --
 * the one failure this work sample cannot afford.
 *
 * This test extracts the core between the markers /*CORE:BEGIN* / and /*CORE:END* /
 * from app/index.html, runs it without a browser, and compares its output against
 * data/metrics.json, which Python produced from the same dataset.
 *
 * Interface contract (binding for frontend-engineer and analytics-engineer)
 * ------------------------------------------------------------------------
 * The extracted source must:
 *   1. run without any DOM -- no document, no window, no fetch;
 *   2. end by defining a `const CockpitCore = { ... }`;
 *   3. expose at least these functions:
 *
 *      CockpitCore.aggregate(dataset, filter) -> sums of the additive fields
 *          `filter` accepts { markets, channels, partners, productGroups, articles,
 *          weekFrom, weekTo },
 *          each optional; omitted keys mean "all".
 *
 *      CockpitCore.computeKpis(aggregate) -> { <kpi_key>: number | null }
 *          Ratios as quotient of sums (decision A3); null when the denominator is
 *          zero or below the minimum sample size (GF2 in docs/SPEC.md).
 *
 *      CockpitCore.scenario(dataset, { volumeIncrease, expansionQuarter })
 *          -> { perPartner: { <partner>: { weeks: [...], bottleneckWeeks: [...] } } }
 *
 * Run with:  node --test "tests/js/*.test.mjs"
 * (Node 22 treats a bare directory argument as a module path, not as a
 *  test directory -- the quoted pattern is the form that works.)
 */

import { test, describe, before } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const APP = join(ROOT, "app", "index.html");
const METRICS = join(ROOT, "data", "metrics.json");

const BEGIN = "/*CORE:BEGIN*/";
const END = "/*CORE:END*/";

/** Pull the calculation core out of the single-file app. */
export function extractCore(html) {
  const start = html.indexOf(BEGIN);
  const stop = html.indexOf(END);
  if (start === -1 || stop === -1) {
    throw new Error(
      `Marker ${BEGIN} / ${END} fehlen in app/index.html (NFR-13). ` +
        "Der Rechenkern muss zwischen den Markern liegen, damit er ohne Browser testbar ist."
    );
  }
  if (stop < start) {
    throw new Error(`${END} steht vor ${BEGIN} in app/index.html`);
  }
  return html.slice(start + BEGIN.length, stop);
}

/**
 * Evaluate the core in an empty context. Any access to document or window throws
 * here, which is exactly the point: the core must be free of DOM dependencies.
 */
export function loadCore(source) {
  const context = vm.createContext({ console });
  vm.runInContext(`${source}\n;globalThis.__core = CockpitCore;`, context, {
    timeout: 5000,
    filename: "cockpit-core.js",
  });
  const core = context.__core;
  if (!core || typeof core !== "object") {
    throw new Error("Der Rechenkern definiert kein Objekt 'CockpitCore'.");
  }
  return core;
}

/**
 * Values returned from the sandbox belong to a different realm, so their prototype
 * is not the one assert.deepEqual() expects. Round-tripping through JSON compares
 * the data instead of the object identity.
 */
export function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

/** Read the embedded dataset the same way the browser does. */
export function extractEmbeddedData(html) {
  const match = html.match(
    /<script[^>]*id=["']cockpit-data["'][^>]*>([\s\S]*?)<\/script>/i
  );
  if (!match) {
    throw new Error('Datenblock <script id="cockpit-data"> fehlt in app/index.html');
  }
  return JSON.parse(match[1]);
}

const appAvailable = existsSync(APP) && existsSync(METRICS);

describe("Rechenkern des Cockpits", { skip: appAvailable ? false : "app/index.html oder data/metrics.json existiert noch nicht" }, () => {
  let core;
  let embedded;
  let metrics;

  before(() => {
    const html = readFileSync(APP, "utf8");
    core = loadCore(extractCore(html));
    embedded = extractEmbeddedData(html);
    metrics = JSON.parse(readFileSync(METRICS, "utf8"));
  });

  test("stellt die vereinbarte Schnittstelle bereit", () => {
    for (const name of ["aggregate", "computeKpis", "scenario"]) {
      assert.equal(
        typeof core[name],
        "function",
        `CockpitCore.${name}() fehlt -- siehe Schnittstellenvertrag in dieser Datei`
      );
    }
  });

  test("kommt ohne DOM aus", () => {
    // loadCore() already ran the source in a context without document/window.
    // Reaching this point proves the core did not touch either of them.
    assert.ok(core, "Rechenkern liess sich ohne Browser laden");
  });

  test("eingebettete Daten stimmen mit data/metrics.json ueberein", () => {
    assert.deepEqual(
      embedded.metrics,
      metrics,
      "Die in app/index.html eingebetteten Kennzahlen weichen von data/metrics.json ab. " +
        "Bitte 'python data/build_app.py' ausfuehren."
    );
  });

  test("berechnet dieselben Kennzahlen wie die Python-Auswertung", () => {
    const totals = core.aggregate(embedded.dataset, {});
    const computed = plain(core.computeKpis(totals));
    const expected = metrics.kpis;

    assert.ok(expected, "metrics.json enthaelt keinen Block 'kpis'");

    const deviations = [];
    for (const [key, entry] of Object.entries(expected)) {
      const reference = typeof entry === "object" && entry !== null ? entry.value : entry;
      if (typeof reference !== "number") continue;

      const actual = computed[key];
      assert.equal(
        typeof actual,
        "number",
        `Kennzahl '${key}' fehlt im JavaScript-Rechenkern`
      );

      // Four significant decimals: enough to catch a real formula difference,
      // tolerant of floating point summation order.
      const tolerance = Math.max(Math.abs(reference) * 1e-9, 1e-9);
      if (Math.abs(actual - reference) > tolerance) {
        deviations.push(`${key}: JavaScript ${actual} vs. Python ${reference}`);
      }
    }
    assert.deepEqual(deviations, [], `Abweichungen zwischen Tool und Auswertung:\n${deviations.join("\n")}`);
  });

  test("Teilmengen summieren sich zur Gesamtmenge", () => {
    const totals = plain(core.aggregate(embedded.dataset, {}));
    const markets = metrics.dimensions?.markets ?? ["DE", "FR", "IT", "GB", "PL", "NL", "SE", "NO", "DK", "FI"];

    const summed = markets
      .map((market) => plain(core.aggregate(embedded.dataset, { markets: [market] })))
      .reduce((accumulator, part) => {
        for (const [key, value] of Object.entries(part)) {
          if (typeof value === "number") {
            accumulator[key] = (accumulator[key] ?? 0) + value;
          }
        }
        return accumulator;
      }, {});

    for (const [key, total] of Object.entries(totals)) {
      if (typeof total !== "number") continue;
      const tolerance = Math.max(Math.abs(total) * 1e-9, 1e-6);
      assert.ok(
        Math.abs(summed[key] - total) <= tolerance,
        `Feld '${key}': Summe ueber die Maerkte (${summed[key]}) weicht vom Gesamtwert (${total}) ab`
      );
    }
  });
});

describe("Extraktion des Rechenkerns", () => {
  test("findet den Kern zwischen den Markern", () => {
    const html = `<html><script>
      ${BEGIN}
      const CockpitCore = { aggregate: () => ({ orders: 2 }), computeKpis: (a) => ({ x: a.orders / 4 }), scenario: () => ({}) };
      ${END}
    </script></html>`;
    const core = loadCore(extractCore(html));
    assert.equal(typeof core.aggregate, "function");
    assert.deepEqual(plain(core.computeKpis(core.aggregate())), { x: 0.5 });
  });

  test("meldet fehlende Marker mit einem verwertbaren Hinweis", () => {
    assert.throws(() => extractCore("<html>ohne Marker</html>"), /Marker .* fehlen/);
  });

  test("laesst den Kern nicht auf das DOM zugreifen", () => {
    const html = `${BEGIN} const CockpitCore = { x: document.title }; ${END}`;
    assert.throws(() => loadCore(extractCore(html)), /document is not defined/);
  });

  test("liest den eingebetteten Datenblock wie der Browser", () => {
    const html = `<script id="cockpit-data" type="application/json">{"dataset":{"rows":[]},"metrics":{"a":1}}</script>`;
    assert.deepEqual(extractEmbeddedData(html), { dataset: { rows: [] }, metrics: { a: 1 } });
  });
});
