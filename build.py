"""Rebuild the whole project from scratch, in the one order that is correct.

    python build.py              # full rebuild, then run the tests
    python build.py --skip-tests # rebuild only
    python build.py --tool-url "https://<konto>.github.io/<repo>/app/"

The address of the published cockpit lives in one place: ``site.json`` at the
repository root. ``--tool-url`` overrides it for a single run. The build passes
it to the case study and writes it into the marked block of the README.

Why a single script
-------------------
Every number in the cockpit, the management report and the case study comes from
one generated dataset. That only stays true if the chain is rebuilt in order:
a new dataset without recomputed metrics, or recomputed metrics without a fresh
injection into the HTML file, produces two documents that disagree -- exactly the
failure this project cannot afford.

Steps that do not exist yet are reported and skipped, so the script is usable
while the project is still being assembled.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site.json"
README = ROOT / "README.md"
README_BEGIN = "<!-- TOOL_URL:BEGIN -->"
README_END = "<!-- TOOL_URL:END -->"


def site_tool_url() -> str | None:
    """The tool address from site.json, or None as long as it is not published."""
    import json

    if not SITE.exists():
        return None
    value = json.loads(SITE.read_text(encoding="utf-8")).get("tool_url") or ""
    return value.strip() or None


def update_readme(tool_url: str | None) -> None:
    """Write the address into the marked README block -- the README never guesses it."""
    if not README.exists():
        return
    text = README.read_text(encoding="utf-8")
    if README_BEGIN not in text or README_END not in text:
        return
    if tool_url:
        body = f"Das Cockpit ist veröffentlicht unter: <{tool_url}>"
    else:
        body = ("Noch nicht veröffentlicht -- sobald die Adresse in `site.json` steht, "
                "trägt `python build.py` sie hier und in der Case Study ein.")
    start = text.index(README_BEGIN) + len(README_BEGIN)
    end = text.index(README_END)
    new = text[:start] + "\n" + body + "\n" + text[end:]
    if new != text:
        README.write_text(new, encoding="utf-8", newline="\n")


class Step:
    def __init__(
        self,
        title: str,
        script: str,
        args: list[str] | None = None,
        requires: list[str] | None = None,
    ):
        self.title = title
        self.script = script
        self.args = args or []
        # Inputs the step needs. While the project is being assembled these may not
        # exist yet -- that is "not this step's turn", not a failure.
        self.requires = requires or []

    @property
    def path(self) -> Path:
        return ROOT / self.script

    def run(self) -> str:
        """Return 'ok', 'missing' or 'failed'."""
        if not self.path.exists():
            print(f"  uebersprungen -- {self.script} existiert noch nicht")
            return "missing"

        absent = [name for name in self.requires if not (ROOT / name).exists()]
        if absent:
            print(f"  uebersprungen -- Eingabe fehlt noch: {', '.join(absent)}")
            return "missing"

        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(self.path), *self.args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        duration = time.monotonic() - started

        for line in (result.stdout or "").splitlines():
            print(f"  | {line}")
        if result.returncode != 0:
            for line in (result.stderr or "").splitlines():
                print(f"  ! {line}")
            print(f"  FEHLGESCHLAGEN nach {duration:.1f}s (Rueckgabewert {result.returncode})")
            return "failed"

        print(f"  fertig in {duration:.1f}s")
        return "ok"


def run_command(title: str, command: list[str]) -> str:
    print(f"\n== {title} ==")
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    output = (result.stdout or "") + (result.stderr or "")
    for line in output.splitlines()[-25:]:
        print(f"  | {line}")
    return "ok" if result.returncode == 0 else "failed"


def main() -> int:
    # Die Windows-Konsole laeuft unter cp1252 und kann weder Umlaute aus den
    # Unterprozessen noch das Ersatzzeichen U+FFFD darstellen, das beim Lesen
    # ihrer Ausgabe entsteht. Ohne diese Zeile bricht build.py mitten im ersten
    # Schritt mit einem UnicodeEncodeError ab -- ausgerechnet der Befehl, den die
    # README als Erstes nennt (Entscheidung P3).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--skip-tests", action="store_true", help="nur bauen, nicht testen")
    parser.add_argument(
        "--tool-url",
        default=None,
        help="oeffentliche Adresse des Cockpits; Standard ist tool_url aus site.json",
    )
    args = parser.parse_args()

    tool_url = args.tool_url or site_tool_url()
    case_study_args = ["--tool-url", tool_url] if tool_url else []
    update_readme(tool_url)

    steps = [
        Step("1/4  Datensatz erzeugen", "data/generate_data.py"),
        Step("2/4  Kennzahlen und automatische Analyse berechnen", "data/compute_metrics.py"),
        Step(
            "3/4  Daten in app/index.html einbetten",
            "data/build_app.py",
            requires=["app/index.html", "data/dataset.json", "data/metrics.json"],
        ),
        Step(
            "4/4  Case Study rendern und als PDF ausgeben",
            "case-study/build_case_study.py",
            case_study_args,
            requires=["data/metrics.json", "case-study/template/case_study.template.html"],
        ),
    ]

    results: dict[str, str] = {}
    for step in steps:
        print(f"\n== {step.title} ==")
        results[step.title] = step.run()
        if results[step.title] == "failed":
            print("\nAbbruch: Ein Schritt ist fehlgeschlagen. "
                  "Die nachfolgenden Schritte wuerden auf veralteten Daten aufsetzen.")
            return 1

    if not args.skip_tests:
        results["Python-Tests"] = run_command(
            "Python-Tests", [sys.executable, "-m", "pytest", "tests/", "-q"]
        )
        results["JavaScript-Test"] = run_command(
            "JavaScript-Test", ["node", "--test", "tests/js/*.test.mjs"]
        )
        if (ROOT / "app" / "index.html").exists():
            results["Cockpit im Browser"] = run_command(
                "Cockpit im Browser", ["node", "tools/check_app.mjs"]
            )
            results["Cockpit ohne Netz"] = run_command(
                "Cockpit ohne Netz (NFR-03)", ["node", "tools/check_app.mjs", "--offline"]
            )

    print("\n" + "=" * 60)
    print("Ergebnis")
    print("=" * 60)
    label = {"ok": "ok       ", "missing": "fehlt    ", "failed": "FEHLER   "}
    for title, outcome in results.items():
        print(f"  {label[outcome]} {title}")

    missing = [t for t, outcome in results.items() if outcome == "missing"]
    failed = [t for t, outcome in results.items() if outcome == "failed"]

    if missing:
        print(f"\n{len(missing)} Schritt(e) noch nicht vorhanden -- das Projekt ist im Aufbau.")
    if failed:
        print(f"\n{len(failed)} Schritt(e) fehlgeschlagen.")
        return 1
    if not missing:
        print("\nVollstaendiger Neuaufbau erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
