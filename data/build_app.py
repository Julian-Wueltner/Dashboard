"""Embed dataset and metrics into the single-file cockpit (decision A4).

``app/index.html`` must run from a double click, so it cannot fetch its data at
runtime -- browsers refuse network requests to the file system. Instead this script
writes the JSON payload into a marker block inside the HTML file:

    <script id="cockpit-data" type="application/json">...</script>

That keeps the promise of a single self-contained file *and* the promise that no
number is ever typed into the markup by hand (hard rule 5).

Usage
-----
    python data/build_app.py                 # inject dataset + metrics
    python data/build_app.py --check         # verify the file is up to date

The ``--check`` mode is used by the tests and by QA: it fails when the embedded
payload differs from the current data files, which would mean the tool shows other
numbers than the report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_APP = ROOT / "app" / "index.html"
DEFAULT_DATASET = ROOT / "data" / "dataset.json"
DEFAULT_METRICS = ROOT / "data" / "metrics.json"

# The marker block the frontend must provide. Everything between the tags is
# owned by this script and replaced on every build.
BLOCK_PATTERN = re.compile(
    r'(<script\b[^>]*\bid=["\']cockpit-data["\'][^>]*>)(.*?)(</script>)',
    re.DOTALL | re.IGNORECASE,
)


def show(path: Path) -> str:
    """Path relative to the project root when possible, absolute otherwise."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


class BuildError(RuntimeError):
    """Raised when the app file or the data files are not in a usable state."""


def load_json(path: Path) -> object:
    if not path.exists():
        raise BuildError(f"Datei fehlt: {show(path)}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BuildError(f"{show(path)} ist kein gueltiges JSON: {error}")


def encode_payload(dataset: object, metrics: object) -> str:
    """Serialise the payload so it is safe inside an HTML script element.

    ``</script>`` anywhere in the data would end the block early, so every angle
    bracket and ampersand is escaped as a JSON unicode sequence. The result is
    still valid JSON and ``JSON.parse`` restores the original characters.
    """
    payload = {"dataset": dataset, "metrics": metrics}
    # No sort_keys here, deliberately. The order of ``metrics.kpis`` carries
    # meaning: it is the order the tiles appear in, fixed by AK-01.1 and table 1
    # of docs/KPI_DEFINITIONS.md. Sorting alphabetically silently rearranged the
    # overview -- capacity utilisation first, lead time fourth -- with nothing in
    # the frontend to blame. Determinism does not need sorting: json.loads keeps
    # the order of the file, and Python dicts preserve insertion order, so the
    # same input always produces the same output.
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def read_embedded_payload(html: str) -> str:
    match = BLOCK_PATTERN.search(html)
    if not match:
        raise BuildError(
            'Marker fehlt in app/index.html: <script id="cockpit-data" type="application/json">'
        )
    return match.group(2).strip()


def inject(html: str, payload: str) -> str:
    match = BLOCK_PATTERN.search(html)
    if not match:
        raise BuildError(
            'Marker fehlt in app/index.html: <script id="cockpit-data" type="application/json">'
        )
    return html[: match.start(2)] + payload + html[match.end(2) :]


def build(app_path: Path, dataset_path: Path, metrics_path: Path, check_only: bool) -> int:
    if not app_path.exists():
        raise BuildError(f"Datei fehlt: {show(app_path)}")

    payload = encode_payload(load_json(dataset_path), load_json(metrics_path))
    html = app_path.read_text(encoding="utf-8")
    embedded = read_embedded_payload(html)

    if check_only:
        if embedded != payload:
            print(
                "Die eingebetteten Daten sind nicht aktuell. "
                "Bitte 'python data/build_app.py' ausfuehren.",
                file=sys.stderr,
            )
            return 1
        print("Eingebettete Daten sind aktuell.")
        return 0

    if embedded == payload:
        print("Eingebettete Daten waren bereits aktuell -- keine Aenderung.")
    else:
        app_path.write_text(inject(html, payload), encoding="utf-8", newline="\n")
        print(f"Daten eingebettet in {show(app_path)}")

    size_mb = app_path.stat().st_size / 1024 / 1024
    print(f"Dateigroesse: {size_mb:.2f} MB (Grenze 1,50 MB)")
    if size_mb >= 1.5:
        print("WARNUNG: Die Datei ueberschreitet die Groessengrenze.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--app", type=Path, default=DEFAULT_APP)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument(
        "--check",
        action="store_true",
        help="nur pruefen, ob die eingebetteten Daten dem aktuellen Stand entsprechen",
    )
    args = parser.parse_args()

    try:
        return build(args.app, args.dataset, args.metrics, args.check)
    except BuildError as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
