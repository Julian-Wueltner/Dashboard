"""Render an HTML file to PDF with a Chromium browser and verify the result.

Used by ``case-study/build_case_study.py``. Kept separate because the awkward
parts -- finding the browser, the profile directory Chrome silently needs, and
reading the page count back out of the PDF -- have nothing to do with writing a
case study, and because the page-count check is a hard acceptance criterion
rather than a nicety.

    from tools.pdf import html_to_pdf, pdf_page_count

    result = html_to_pdf(source, target, expect_pages=2, max_kb=700)

``html_to_pdf`` raises ``PdfError`` when the document does not have the expected
number of pages or exceeds the size limit. That is deliberate: a three-page
"two-page case study" must break the build, not produce a warning somebody reads
later.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

BROWSER_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


class PdfError(RuntimeError):
    """The PDF could not be produced, or does not meet the acceptance criteria."""


@dataclass
class PdfResult:
    path: Path
    pages: int
    size_kb: float

    def __str__(self) -> str:
        return f"{self.path.name}: {self.pages} Seiten, {self.size_kb:.0f} KB"


def find_browser() -> Path:
    """Locate an installed Chromium browser (decision A2)."""
    for candidate in BROWSER_CANDIDATES:
        if candidate.exists():
            return candidate
    for name in ("chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return Path(found)
    raise PdfError(
        "Kein Chromium-Browser gefunden. Chrome oder Edge installieren, oder den "
        "Pfad in tools/pdf.py ergaenzen. Alternative waere Playwright oder WeasyPrint "
        "(siehe Entscheidung A2)."
    )


def pdf_page_count(raw: bytes) -> int:
    """Read the number of pages out of a PDF.

    Chromium writes an uncompressed page tree, so the ``/Count`` entry of the root
    node is readable directly. Counting ``/Type /Page`` objects is the fallback.
    """
    counts = [int(value) for value in re.findall(rb"/Count\s+(\d+)", raw)]
    if counts:
        return max(counts)
    return len(re.findall(rb"/Type\s*/Page[^s]", raw))


def _wait_for_file(target: Path, appear_timeout: float = 30.0) -> bool:
    """Wait until the file exists and has stopped growing."""
    deadline = time.monotonic() + appear_timeout
    while time.monotonic() < deadline:
        if target.exists() and target.stat().st_size > 0:
            break
        time.sleep(0.2)
    else:
        return False

    # The browser streams the PDF out; only a size that stays put twice is final.
    previous = -1
    for _ in range(50):
        size = target.stat().st_size
        if size == previous and size > 0:
            return True
        previous = size
        time.sleep(0.2)
    return target.stat().st_size > 0


def html_to_pdf(
    source: Path,
    target: Path,
    *,
    expect_pages: int | None = None,
    max_kb: float | None = None,
    timeout: int = 120,
) -> PdfResult:
    """Render ``source`` to ``target`` and check the result against the limits."""
    source = Path(source).resolve()
    target = Path(target).resolve()
    if not source.exists():
        raise PdfError(f"Quelldatei fehlt: {source}")

    browser = find_browser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    # Chrome keeps a lock on its profile for a moment after the launcher returns,
    # so cleanup errors must not fail the build.
    with tempfile.TemporaryDirectory(
        prefix="cockpit-pdf-", ignore_cleanup_errors=True
    ) as profile:
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            # Without its own profile directory Chrome exits 0 and writes no file
            # at all -- verified on 2026-09-22, see decision A2.
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={target}",
            source.as_uri(),
        ]
        try:
            subprocess.run(command, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise PdfError(f"Der Browser hat nach {timeout}s nicht geantwortet.")

        # On Windows the chrome.exe that was started is only a launcher: it exits
        # immediately while the real browser process keeps running and writes the
        # file a moment later (measured: about two seconds). Without this wait the
        # build would fail at random.
        if not _wait_for_file(target):
            raise PdfError(
                f"Der Browser hat keine Datei geschrieben: {target}. "
                "Meist fehlt der Schalter --user-data-dir oder der Zielordner ist gesperrt."
            )

    raw = target.read_bytes()
    result = PdfResult(path=target, pages=pdf_page_count(raw), size_kb=len(raw) / 1024)

    problems = []
    if expect_pages is not None and result.pages != expect_pages:
        problems.append(
            f"Das PDF hat {result.pages} Seiten, gefordert sind genau {expect_pages}. "
            "Meist hilft: Abstaende oder Schriftgroesse leicht reduzieren, oder einen "
            "Absatz kuerzen -- nicht den Seitenumbruch erzwingen."
        )
    if max_kb is not None and result.size_kb > max_kb:
        problems.append(
            f"Das PDF ist {result.size_kb:.0f} KB gross, erlaubt sind hoechstens "
            f"{max_kb:.0f} KB. Grafiken gehoeren als Inline-SVG in das Dokument, "
            "nicht als Rasterbild."
        )
    if problems:
        raise PdfError(" ".join(problems))

    return result
