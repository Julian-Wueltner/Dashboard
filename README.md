# International Sales Cockpit

**Demo für einen europäischen Industriehersteller**

> Demo mit fiktiven Daten · eigene Initiative · erstellt mit KI-Unterstützung

Ein interaktives Steuerungscockpit für den internationalen Vertrieb eines Herstellers modularer
Metallkomponenten für den Anlagenbau — zehn Märkte, drei Vertriebswege (Tochtergesellschaft,
Handelsvertretung, Direktvertrieb ab Werk), sechs Vertriebspartner. Dazu eine zweiseitige Case Study als
Management-Report. Alle Daten sind erfunden und mit einem festen Zufallswert erzeugt; es werden keine realen
Unternehmen, Marken oder Dienstleister dargestellt.

Das Projekt ist eine Arbeitsprobe: Es zeigt eine vollständige Fallbearbeitung — von einer auffälligen
Vertriebskennzahl über die Analyse und die Entscheidungsvorlage bis zum Management-Report.

<!-- TOOL_URL:BEGIN -->
Das Cockpit ist veröffentlicht unter: <https://julian-wueltner.github.io/Dashboard/>
<!-- TOOL_URL:END -->

---

## Schnellstart

**Nur ansehen:** `app/index.html` per Doppelklick öffnen. Kein Server, kein Build, keine Installation.
Im Cockpit oben auf **„Demo-Fall starten"** klicken — der Ablauf führt in sechs Schritten durch den Fall.

**Selbst neu bauen — ein Befehl:**

```bash
python -m pip install -r requirements.txt
python build.py                       # baut die ganze Kette und laesst danach alle Tests laufen
```

**Oder Schritt für Schritt:**

```bash
python data/generate_data.py          # Datensatz erzeugen (fester Seed, reproduzierbar)
python data/compute_metrics.py        # Kennzahlen und automatische Analyse berechnen
python data/build_app.py              # Daten in app/index.html einbetten
python case-study/build_case_study.py # Case Study rendern und als PDF ausgeben

python -m pytest tests/ -q            # Python-Tests
node --test "tests/js/*.test.mjs"     # Test des JavaScript-Rechenkerns
node tools/check_app.mjs             # Cockpit im Browser starten und pruefen
node tools/check_app.mjs --offline   # dasselbe ohne Netz (Ersatzdarstellung)
node tools/check_ui.mjs              # zwanzig harte Aussagen ueber das
                                     # gerenderte Dokument
node tools/check_print.mjs           # Drucklayout: je genau eine A4-Seite
python tools/zeige_fehlalarme.py     # Fehlalarme je Stufe der Erkennungsregel
```

Voraussetzungen: Python 3.11 oder neuer, Node 18 oder neuer (nur für den JavaScript-Test), ein installierter
Chromium-Browser (Chrome oder Edge) für die PDF-Ausgabe.

---

## Was die sieben Module zeigen — und welche Aufgabe sie abdecken

| Aufgabe im internationalen Vertrieb | Modul im Cockpit | Was dort konkret passiert |
|---|---|---|
| **Marktanalyse** — wie stehen die Märkte gegen Ziel und Vorjahr? | **Übersicht** | Zehn Kennzahlenkacheln mit Ampel und Trend, frei filterbar nach Markt, Vertriebsweg, Vertriebspartner und Zeitraum. Jede Kennzahl ist genau einem Fachbereich zugeordnet. |
| **Vertriebsprozess steuern** — wo klemmt es zwischen Anfrage und After-Sales? | **Vertriebsprozess** | Fünf Stufen — Anfrage → Angebot, Angebot → Auftrag, Auftragserfassung, Fertigung und Versand, After-Sales — je Stufe Durchlaufzeit, Zielwert und verantwortlicher Bereich; der Engpass ist hervorgehoben. |
| **Partner führen** — Tochtergesellschaften und Handelsvertretungen | **Partner-Scorecard** | Je Partner und Markt: Angebotserfolgsquote, Liefertreue, Deckungsbeitrag je Auftrag, Aktivitätsgrad und eine Gesamtampel gegen den Zielwert; darunter die Auslastung der Angebotskapazität je Partner. |
| **Handlungsfelder erkennen** | **Auffälligkeiten** | Die automatische Analyse prüft die Zeitreihen auf der Ebene, auf der sie gesteuert werden, und meldet, was auffällig **und** fachlich relevant ist — mit offengelegter Wirkungsschätzung und Effizienzpotenzial. |
| **Projekte umsetzen** — von der Anforderung bis zur Bewertung | **Maßnahmen** | Aus einer Auffälligkeit wird per Klick eine Maßnahme mit fünf Phasen, Verantwortlichem und Terminen. Eine abgeschlossene Maßnahme zeigt den **Vorher-nachher-Vergleich** mit echten Zahlen. |
| **Marktaufbau planen** | **Wachstumsszenario** | Schieberegler für 0 bis 40 % Mehrvolumen und ein Schalter „eigene Tochtergesellschaft in Skandinavien ab Quartal X"; zeigt, ab wann die Vertretungen an ihre Grenzen stoßen, was eine eigene Gesellschaft ändert, und leitet Roadmap-Punkte ab. |
| **Entscheidungsvorlagen und Reports** | **Report & Entscheidungsvorlage** | Ein Klick erzeugt einen druckfähigen Management-Report und eine Entscheidungsvorlage mit drei bewerteten Optionen, klarer Empfehlung und Eskalationstrigger. |

---

## Der rote Faden der Demo

Im Datensatz stecken vier Auffälligkeiten, die die automatische Analyse selbst findet:

1. **Angebotserfolgsquote im Markt SE** fällt ab KW 32 von rund 34 % auf rund 21 % — ein lokaler
   Wettbewerber ist aufgetreten. Betroffen ist Vertretung 4, verantwortlich der Vertrieb.
2. **Eine Woche später** steigt in SE die Angebotsdurchlaufzeit von rund 22 auf rund 39 Stunden, weil mehr
   Angebote nachverhandelt werden — ein zeitlicher Zusammenhang, ausdrücklich kein Ursachennachweis.
3. **Formteil MOD-1042** wird ab KW 37 deutlich häufiger reklamiert als die übrigen Formteile — überwiegend
   wegen Maßabweichung. Verglichen wird gegen die übrigen Artikel derselben Produktgruppe, nicht gegen den
   Gesamtdurchschnitt.
4. **Markt NO** wächst ab KW 20 deutlich; ab KW 41 sinkt der Aktivitätsgrad der Vertretung unter den
   Zielwert und die Angebotsdurchlaufzeit steigt über 24 Stunden. Das ist der Aufhänger des
   Wachstumsszenarios.

Eine fünfte, früher im Jahr aufgetretene Abweichung — die Liefertreue im Markt PL — ist seit KW 14 behoben
und liefert den Vorher-nachher-Vergleich für die abgeschlossene Maßnahme.

Die Entscheidungsvorlage bewertet drei Wege: **A** Preis- und Konditionsanpassung, **B** eigene
Vertriebspräsenz in Skandinavien, **C** die bestehende Vertretung mit Zielvereinbarung und Schulung stärken.
Empfohlen wird C, mit dem festen Trigger, Option B vorzubereiten, wenn die Quote acht Wochen nach Abschluss
der Zielvereinbarung unter dem Zielwert bleibt.

---

## Wie die automatische Analyse arbeitet

Sie vergleicht jede Kennzahl mit den **letzten acht Wochen** (bei Beginn einer Abweichung eingefroren), mit
dem **übrigen Geschäft derselben Woche** und mit dem **vereinbarten Zielwert**. Gemeldet wird nur, was
statistisch auffällig (z-Wert ab 2,5) **und** fachlich relevant ist und den Zielwert verletzt — und das
**zwei Wochen hintereinander**. Verbesserungen lösen keinen Alarm aus, und Auswertungen unterhalb einer
Mindeststichprobe werden gar nicht erst bewertet.

Das ist bewusst **keine** künstliche Intelligenz, sondern eine offengelegte Rechenregel. Jeder Erklärungstext
im Tool ist als „automatisch erstellt" gekennzeichnet. Eine Anbindung an ein Sprachmodell ist nicht
gebaut, und es werden keine Zugangsschlüssel gespeichert.

---

## Eine einzige Datenquelle

Jede Zahl in Tool, Report und Case Study stammt aus derselben erzeugten Datenbasis. Keine Zahl ist von Hand
in einen Text geschrieben:

```
data/generate_data.py  ->  data/dataset.json   (nur additive Messgrößen)
                             |
                             v
data/compute_metrics.py ->  data/metrics.json  (alle abgeleiteten und formatierten Zahlen)
                             |
              +--------------+--------------+
              v                             v
       data/build_app.py            case-study/build_case_study.py
   (bettet Daten in index.html)   (füllt die Platzhalter der Vorlage)
```

Der Datensatz speichert nur Größen, die man addieren darf — „entschiedene Angebote" und „davon gewonnen",
nicht „Erfolgsquote 34 %". Jede Quote entsteht erst durch Division zweier Summen. Nur so liefert jeder Filter
im Cockpit dieselbe Zahl wie die Auswertung im Report.

Die Vorlage der Case Study enthält **keine einzige Ziffer**; ein Test schlägt fehl, sobald dort eine Zahl von
Hand eingetragen wird.

---

## Aufbau des Repositorys

| Pfad | Inhalt |
|---|---|
| `app/index.html` | Das Cockpit — eine einzige selbstständige Datei |
| `index.html`, `.nojekyll` | Weiterleitung auf `app/` und Einstellung für GitHub Pages |
| `data/generate_data.py` | Datengenerator mit festem Seed; `--no-anomalies` erzeugt den Kontrolldatensatz |
| `data/analysis.py` | Kennzahlenformeln, automatische Analyse, Wirkungsabschätzung, Szenariomodell |
| `data/compute_metrics.py` | Erzeugt `data/metrics.json` aus `data/dataset.json` |
| `data/formatting.py` | Die einzige Formatierungsinstanz des Projekts (deutsches Zahlenformat) |
| `data/build_app.py` | Bettet Datensatz und Kennzahlen in `app/index.html` ein |
| `build.py` | Baut die gesamte Kette in der richtigen Reihenfolge und testet |
| `tools/check_app.mjs` | Startet das Cockpit im Browser und meldet Fehler, Ladezeit, Offline-Verhalten |
| `tools/check_ui.mjs` | Prüft zwanzig harte Aussagen über das gerenderte Dokument — Ampeln mit Farbe *und* Symbol *und* Text, Kachelreihenfolge, Filterwirkung, Demo-Fall |
| `tools/check_print.mjs` | Prüft, dass Management-Report und Entscheidungsvorlage je genau eine A4-Seite ergeben |
| `tools/zeige_fehlalarme.py` | Rechnet vor, wie viele Fehlalarme jede weggelassene Bedingung der Erkennungsregel kostet |
| `tools/pdf.py` | Rendert HTML zu PDF und prüft Seitenzahl und Dateigröße |
| `case-study/` | Vorlage, Build-Skript, gerenderte Case Study und PDF |
| `docs/` | Kennzahlenkatalog, Datenannahmen |
| `tests/` | Berechnungen, Anomalieerkennung, Datenkonsistenz, harte Regeln, JavaScript-Rechenkern |

---

## Dokumentation

| Dokument | Wofür |
|---|---|
| [`docs/KPI_DEFINITIONS.md`](docs/KPI_DEFINITIONS.md) | Jede Kennzahl mit Formel, Einheit, Zielwert und Fachbereich |
| [`docs/DATA_ASSUMPTIONS.md`](docs/DATA_ASSUMPTIONS.md) | Welche Annahmen im Datensatz stecken und warum sie plausibel sind |

---

## Wie das Ergebnis geprüft wird

Die Werkzeuge im Ordner `tools/` prüfen die Dinge, die kein Unit-Test erreicht:

```bash
node tools/check_app.mjs             # startet das Cockpit im Browser, meldet
                                     # unbehandelte Ausnahmen und die Ladezeit
node tools/check_app.mjs --offline   # blockiert das Netz: die Wertetabellen
                                     # müssen die Diagramme ersetzen
node tools/check_print.mjs           # druckt Report und Entscheidungsvorlage
                                     # und zählt die Seiten
python tools/zeige_fehlalarme.py     # zeigt auf einem Datensatz ohne Probleme,
                                     # wie viele Fehlalarme jede weggelassene
                                     # Bedingung der Regel kostet
```

Das letzte Werkzeug beantwortet die Frage, die einer automatischen Analyse immer gestellt wird — ob sie
nicht einfach alles meldet:

```
  12 Fehlalarme   nur z-Wert ab 2,5, zwei Wochen in Folge
   0 Fehlalarme   + fachliche Mindestabweichung
   0 Fehlalarme   + Vergleich gegen das übrige Geschäft derselben Woche
   0 Fehlalarme   + Verletzung des vereinbarten Zielwerts (geltende Regel)
```

---

## Grenzen dieser Demo

- **Erfundene Daten.** Sie sind plausibel konstruiert, aber nicht gemessen. Die Zielwerte sind begründete
  Annahmen, keine Branchenkennzahlen aus einer Quelle.
- **Kein Ursachennachweis.** Zusammenhänge zwischen zwei Auffälligkeiten werden als zeitlicher Zusammenhang
  ausgewiesen, nicht als Kausalität.
- **Keine Prognose.** Das Wachstumsszenario ist eine offengelegte Modellrechnung, kein statistisches
  Vorhersagemodell.
- **Keine Persistenz.** Im Tool angelegte Maßnahmen leben nur in der laufenden Sitzung; nach dem Neuladen
  ist der Ausgangszustand wiederhergestellt.

---

## Entstehung

Julian Wültner hat Ziel, Inhalte und Entscheidungen vorgegeben, ein Team spezialisierter KI-Agenten hat die
Umsetzung übernommen, Julian hat geprüft und abgenommen. Die fachlichen Entscheidungen — Kennzahlen,
Zielwerte, Bewertung der Optionen und die Empfehlung — stammen von Julian.
