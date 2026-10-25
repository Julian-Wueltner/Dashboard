"""German number formatting -- the single formatting authority of the project.

Why this module exists
----------------------
Python and JavaScript do not round the same way. ``round()`` in Python uses
banker's rounding (2.5 becomes 2), ``toFixed()`` in JavaScript rounds half away
from zero (2.5 becomes 3). A value like 94.25 % would therefore appear as
"94,2 %" in the case study and as "94,3 %" in the cockpit -- and the consistency
test would be right to call that a contradiction.

The project therefore formats every *reported* number once, here, and stores the
finished string next to the raw value in ``data/metrics.json``:

    "otif_rate_pl": {"value": 0.9425, "text": "94,3 %", "unit": "%"}

The cockpit prints ``text`` for reported figures and only formats values itself
where the user filters interactively -- there is no second document to contradict.

Conventions (DIN 5008, business reporting style)
------------------------------------------------
* decimal comma, thousands separated by a dot from four digits upwards
* a narrow no-break space before %, € and units, so the number never wraps away
  from its unit
* half-up rounding, made explicit via ``decimal`` -- never the platform default
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

# A narrow no-break space: keeps "94,3" and "%" on the same line without the wide
# gap of a normal space.
NNBSP = " "


def _quantize(value: float, decimals: int) -> Decimal:
    """Round half up, the way a commercial calculation is expected to round."""
    exponent = Decimal(1).scaleb(-decimals)
    return Decimal(str(value)).quantize(exponent, rounding=ROUND_HALF_UP)


def number(value: float, decimals: int = 0, *, signed: bool = False) -> str:
    """Format a plain number: ``1234.5`` with one decimal becomes ``1.234,5``.

    Grouping starts at four digits. DIN 5008 permits leaving four-digit numbers
    unseparated, but German business reporting groups every amount from a
    thousand upwards -- "9.200,46 EUR" is what a reader expects in a management
    report, and "9200,46 EUR" reads like a typing error. The project also writes
    "je 1.000 Bestellungen", so anything else would contradict itself.
    """
    rounded = _quantize(value, decimals)
    negative = rounded < 0
    magnitude = abs(rounded)

    whole = int(magnitude)
    integer_text = str(whole)
    if len(integer_text) >= 4:
        integer_text = f"{whole:,}".replace(",", ".")

    text = integer_text
    if decimals > 0:
        fraction = f"{magnitude:.{decimals}f}".split(".")[1]
        text = f"{integer_text},{fraction}"

    if negative:
        return "-" + text
    if signed:
        return "+" + text
    return text


def percent(share: float, decimals: int = 1, *, signed: bool = False) -> str:
    """Format a share (``0.9425``) as a percentage (``94,3 %``)."""
    return number(share * 100, decimals, signed=signed) + NNBSP + "%"


def percentage_points(delta: float, decimals: int = 1) -> str:
    """Format a difference between two percentages (``-3,4 pp``).

    A change from 94 % to 90 % is four *percentage points*, not four percent.
    Keeping the two apart is the difference between a correct report and a
    sloppy one.
    """
    return number(delta * 100, decimals, signed=delta > 0) + NNBSP + "pp"


def euro(value: float, decimals: int = 2, *, signed: bool = False) -> str:
    """Format an amount in euro (``4,85 €``)."""
    return number(value, decimals, signed=signed) + NNBSP + "€"


def euro_thousands(value: float, decimals: int = 1, *, signed: bool = False) -> str:
    """Format a large amount compactly (``12,4 Tsd. €``) for tiles and headlines."""
    return number(value / 1000, decimals, signed=signed) + NNBSP + "Tsd." + NNBSP + "€"


def days(value: float, decimals: int = 1, *, signed: bool = False) -> str:
    """Format a duration in days (``2,3 Tage``)."""
    unit = "Tag" if _quantize(abs(value), decimals) == 1 else "Tage"
    return number(value, decimals, signed=signed) + NNBSP + unit


def hours(value: float, decimals: int = 1, *, signed: bool = False) -> str:
    unit = "Stunde" if _quantize(abs(value), decimals) == 1 else "Stunden"
    return number(value, decimals, signed=signed) + NNBSP + unit


def per_thousand(value: float, decimals: int = 1, *, signed: bool = False) -> str:
    """Contacts per 1,000 orders (``8,4 je 1.000 Bestellungen``)."""
    return number(value, decimals, signed=signed) + NNBSP + "je 1.000 Bestellungen"


def per_hundred(value: float, decimals: int = 1, *, signed: bool = False) -> str:
    """Inquiries per 100 orders (``9,3 je 100 Aufträge``)."""
    return number(value, decimals, signed=signed) + NNBSP + "je 100 Aufträge"


def index(value: float, decimals: int = 1, *, signed: bool = False) -> str:
    """An index against a base of 100 (``102,9``) -- deliberately without a unit sign."""
    return number(value, decimals, signed=signed)


def count(value: float) -> str:
    """Whole numbers: order counts, shipments, contacts."""
    return number(value, 0)


def week(iso_week: int) -> str:
    """Calendar week label (``KW 34``)."""
    return f"KW{NNBSP}{iso_week}"


def week_planned(iso_week: int, weeks_in_year: int = 52) -> str:
    """Planned calendar week; weeks past the year end roll into the next year."""
    if iso_week > weeks_in_year:
        return f"KW{NNBSP}{iso_week - weeks_in_year} im Folgejahr"
    return week(iso_week)


def week_range(first: int, last: int) -> str:
    return f"KW{NNBSP}{first}–{last}"


#: Every formatter that may be referenced from a metric definition, by name.
FORMATTERS = {
    "number": number,
    "percent": percent,
    "percentage_points": percentage_points,
    "euro": euro,
    "euro_thousands": euro_thousands,
    "days": days,
    "hours": hours,
    "per_thousand": per_thousand,
    "per_hundred": per_hundred,
    "index": index,
    "count": count,
}


def render(value: float, formatter: str, **options: object) -> str:
    """Format ``value`` with the named formatter -- used by the metrics builder."""
    if formatter not in FORMATTERS:
        raise KeyError(
            f"Unbekannter Formatierer '{formatter}'. Erlaubt: {sorted(FORMATTERS)}"
        )
    return FORMATTERS[formatter](value, **options)  # type: ignore[arg-type]
