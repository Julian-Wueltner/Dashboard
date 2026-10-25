"""Generator of the synthetic dataset for the International Sales Cockpit.

Scope
-----
Python standard library only (decision A1). One fixed seed, two runs produce
byte-identical files. Every figure of the project comes from the file this script
writes; nothing downstream invents a number.

Storage format (NFR-05, decision OP-1)
--------------------------------------
Every table is stored as ``{"columns": [...], "rows": [[...], ...]}`` instead of a
list of objects with repeated field names. Only ``meta`` and ``parameters`` are
plain objects.

Additive measures only (decision A3)
------------------------------------
No rate, no average and no percentage is stored. "94 % on time" is stored as
``orders_otif`` and ``orders_delivered``; "22 hours quote lead time" is stored as
the *sum* of hours plus the count of quotes. That is what lets the cockpit filter freely and
still reach exactly the numbers the Python analysis reaches.

Reproducibility
---------------
Every random draw uses a ``random.Random`` instance seeded from the global seed and
from the content of the row it belongs to (``rng_for``). Call order therefore does
not influence any value, and ``--no-anomalies`` keeps the identical noise: the five
planted events are deterministic multipliers applied *after* the draws.

Usage
-----
    python data/generate_data.py
    python data/generate_data.py --no-anomalies --out data/dataset_control.json
    python data/generate_data.py --seed 7 --out data/dataset_seed7.json
    python data/generate_data.py --assortment-weekly --out <path>   # size measurement for OP-1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

# --------------------------------------------------------------------------- #
# Global constants
# --------------------------------------------------------------------------- #

SEED = 42
WEEKS = 52
FLOAT_DECIMALS = 3

#: Decision OP-1: assortment rows are condensed into four-week periods when the
#: weekly grain would push data/dataset.json past this limit.
SIZE_LIMIT_BYTES = 900 * 1024
ASSORTMENT_PERIOD_WEEKS = 4

ORDERS_SAMPLE_SIZE = 3000
BASE_INQUIRIES_PER_WEEK = 4000

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "dataset.json"

# --------------------------------------------------------------------------- #
# Dimensions
# --------------------------------------------------------------------------- #

MARKETS = ["DE", "FR", "IT", "GB", "PL", "NL", "SE", "NO", "DK", "FI"]
CHANNELS = ["subsidiary", "agency", "direct"]
PARTNERS = ["partner_1", "partner_2", "partner_3", "partner_4", "partner_5", "partner_6"]
#: Partners that run as a subsidiary of the manufacturer; the rest are agencies.
SUBSIDIARY_PARTNERS = ["partner_1", "partner_2", "partner_3"]
CAPACITY_PARTNERS = PARTNERS

MARKET_SHARE = {"DE": 0.30, "FR": 0.12, "IT": 0.10, "GB": 0.10, "PL": 0.08,
                "NL": 0.08, "SE": 0.08, "NO": 0.06, "DK": 0.05, "FI": 0.03}

#: Every market is served by exactly one sales partner. Subsidiaries run DE, FR, IT,
#: GB and PL; NL and the Nordic markets run through agencies -- the starting point
#: of the growth scenario. partner_4 is the main partner in SE.
PARTNER_OF_MARKET = {
    "DE": "partner_1",
    "FR": "partner_2", "IT": "partner_2",
    "GB": "partner_3", "PL": "partner_3",
    "SE": "partner_4",
    "NO": "partner_5", "DK": "partner_5",
    "NL": "partner_6", "FI": "partner_6",
}

#: Sales channel mix per market. Direct business ex works exists everywhere; the
#: local share runs through the subsidiary or the agency of the market.
CHANNEL_MIX = {
    market: ({"subsidiary": 0.82, "direct": 0.18}
             if PARTNER_OF_MARKET[market] in SUBSIDIARY_PARTNERS
             else {"agency": 0.72, "direct": 0.28})
    for market in MARKETS
}

# --------------------------------------------------------------------------- #
# Seasonality
# --------------------------------------------------------------------------- #

#: Weekly demand factor of an industrial supplier: weak January, steady spring,
#: summer shutdowns KW 28-32, year-end business KW 45-50, quiet last two weeks.
SEASON = [
    0.70, 0.82, 0.88, 0.93, 0.97, 1.00, 1.01, 1.02,   # KW 1-8
    1.03, 1.04, 1.04, 1.03, 1.02, 0.98,               # KW 9-14
    1.00, 1.02, 1.03, 1.04, 1.02, 0.99,               # KW 15-20
    1.01, 1.02, 1.03, 1.02, 1.00, 0.97,               # KW 21-26
    0.93, 0.84, 0.74, 0.70, 0.72, 0.82,               # KW 27-32
    0.94, 1.00, 1.03, 1.05, 1.06, 1.05,               # KW 33-38
    1.04, 1.05, 1.06, 1.05, 1.06, 1.08,               # KW 39-44
    1.14, 1.18, 1.22, 1.24, 1.20, 1.12,               # KW 45-50
    0.82, 0.48,                                       # KW 51-52
]
assert len(SEASON) == WEEKS

# --------------------------------------------------------------------------- #
# Base rates per dimension (all values are reasoned assumptions, see DATA_ASSUMPTIONS)
# --------------------------------------------------------------------------- #

#: Share of incoming inquiries that receive a quote in the same week.
QUOTE_RATE = {"subsidiary": 0.93, "agency": 0.91, "direct": 0.89}
#: Share of open quotes on which the customer decides in the week.
DECISION_RATE = 0.94
#: Quote success rate: won quotes per decided quote.
WIN_RATE = {"subsidiary": 0.325, "agency": 0.345, "direct": 0.290}
WIN_MARKET_FACTOR = {"DE": 1.00, "FR": 0.98, "IT": 0.97, "GB": 1.01, "PL": 1.03,
                     "NL": 1.00, "SE": 1.03, "NO": 1.01, "DK": 0.99, "FI": 0.98}
ORDER_SHIP_RATE = 0.986
DELIVERED_SHARE = 0.996
LINES_PER_ORDER = 6.5

#: Hours per process stage of the sales process.
STAGE1_INQUIRY_TO_QUOTE = {"subsidiary": 20.0, "agency": 21.5, "direct": 23.0}
STAGE2_QUOTE_TO_ORDER = {"subsidiary": 205.0, "agency": 220.0, "direct": 195.0}
STAGE3_ORDER_ENTRY = {"subsidiary": 9.0, "agency": 11.0, "direct": 8.0}
STAGE4_PRODUCTION_SHIPPING = {"DE": 170.0, "FR": 182.0, "IT": 186.0, "GB": 190.0,
                              "PL": 178.0, "NL": 176.0, "SE": 184.0, "NO": 188.0,
                              "DK": 180.0, "FI": 190.0}
STAGE5_COMPLAINT = {"subsidiary": 96.0, "agency": 104.0, "direct": 100.0}

ON_TIME_IN_FULL = {"DE": 0.962, "FR": 0.955, "IT": 0.951, "GB": 0.953, "PL": 0.957,
                   "NL": 0.958, "SE": 0.956, "NO": 0.953, "DK": 0.957, "FI": 0.952}

COMPLAINT_RATE = 0.0100
COMPLAINT_MARKET_FACTOR = {"DE": 0.95, "FR": 1.02, "IT": 1.06, "GB": 1.00, "PL": 1.04,
                           "NL": 0.96, "SE": 1.10, "NO": 1.00, "DK": 0.97, "FI": 1.02}
COMPLAINT_CLOSED_SHARE = 0.96

#: Delivery date inquiries per 100 orders.
DELIVERY_INQUIRIES = {"subsidiary": 8.8, "agency": 9.8, "direct": 10.6}
DELIVERY_INQUIRY_MARKET_FACTOR = {"DE": 0.95, "FR": 1.02, "IT": 1.08, "GB": 1.00, "PL": 1.03,
                                  "NL": 0.97, "SE": 0.98, "NO": 1.02, "DK": 0.99, "FI": 1.04}

#: Revenue per order in euro and contribution margin ratio.
REVENUE_PER_ORDER = 4800.0
PRICE_LEVEL = {"DE": 1.00, "FR": 0.98, "IT": 0.95, "GB": 1.02, "PL": 0.86,
               "NL": 1.00, "SE": 1.05, "NO": 1.12, "DK": 1.04, "FI": 1.00}
MARGIN_RATE = {"subsidiary": 0.262, "agency": 0.252, "direct": 0.275}
#: Revenue growth against the prior-year week (planning view).
MARKET_GROWTH = {"DE": 1.03, "FR": 1.02, "IT": 0.99, "GB": 1.01, "PL": 1.06,
                 "NL": 1.04, "SE": 1.05, "NO": 1.04, "DK": 1.02, "FI": 0.98}

#: Key accounts per market and the share with a documented sales contact per week.
KEY_ACCOUNTS = 4000
ACTIVITY_RATE = {"subsidiary": 0.920, "agency": 0.905, "direct": 0.890}

#: Cost rates for the impact estimates.
QUOTE_COST = {"subsidiary": 118.0, "agency": 96.0, "direct": 124.0}
COMPLAINT_COST_PER_LINE = 185.0
SERVICE_COST_PER_INQUIRY = 9.40

#: Quote capacity of the sales organisation of each partner.
PLANNING_UTILISATION = 0.80
CAPACITY_ROUNDING = 10
CAPACITY_FLEX_SHARE = 0.15
QUOTES_PER_STAFF_HOUR = {"partner_1": 0.42, "partner_2": 0.40, "partner_3": 0.40,
                         "partner_4": 0.45, "partner_5": 0.45, "partner_6": 0.44}

# --------------------------------------------------------------------------- #
# Planted deviations (decision A7)
# --------------------------------------------------------------------------- #

#: 1) Quote success rate in SE breaks in from KW 32 (a local competitor enters).
SE_MARKET = "SE"
SE_PARTNER = "partner_4"
SE_WIN_RATE = {32: 0.235, 33: 0.215}
SE_WIN_RATE_STEADY = 0.210
SE_WIN_START = 32

#: 2) Follow-on effect: quotes in SE are renegotiated, the quote lead time rises
#: one week later.
SE_QUOTE_EXTRA_HOURS = {33: 10.0, 34: 15.0}
SE_QUOTE_EXTRA_HOURS_STEADY = 19.0
SE_QUOTE_START = 33

#: 3) Article problem: one moulded part with a dimensional deviation, from KW 37.
ARTICLE_ISSUE_ID = "MOD-1042"
ARTICLE_ISSUE_START_WEEK = 37
ARTICLE_ISSUE_COMPLAINT_RATE = 0.039
ARTICLE_ISSUE_REASONS = {
    "complaint_lines_reason_dimension": 0.64,
    "complaint_lines_reason_surface": 0.10,
    "complaint_lines_reason_material": 0.12,
    "complaint_lines_reason_transport": 0.05,
    "complaint_lines_reason_wrong_item": 0.03,
    "complaint_lines_reason_other": 0.06,
}

#: 4) Growth bottleneck NO: demand grows from KW 20, the agency loses touch with its
#: key accounts and the quote lead time leaves the target from KW 41.
NO_MARKET = "NO"
NO_PARTNER = "partner_5"
NO_GROWTH_START = 20
NO_GROWTH_STEP = 0.025
NO_GROWTH_MAX = 1.45
NO_ACTIVITY_DRIFT_START = 30
NO_ACTIVITY_DRIFT_PER_WEEK = 0.002
NO_ACTIVITY = {41: 0.785, 42: 0.770}
NO_ACTIVITY_STEADY = 0.760
NO_QUOTE_EXTRA_HOURS = {41: 6.0, 42: 8.0}
NO_QUOTE_EXTRA_HOURS_STEADY = 9.5
NO_BOTTLENECK_START = 41

#: 5) Already fixed deviation: on-time-in-full in PL, KW 5-13, measure effective KW 14.
PL_MARKET = "PL"
PL_OTIF = {
    5: 0.872, 6: 0.861, 7: 0.855, 8: 0.858, 9: 0.851,
    10: 0.856, 11: 0.862, 12: 0.866, 13: 0.874,
}
PL_OTIF_AFTER = 0.961
PL_OTIF_FIXED_FROM = 14

# --------------------------------------------------------------------------- #
# Article master data
# --------------------------------------------------------------------------- #

PRODUCT_GROUPS = ["Standardmodule", "Formteile", "Verbindungselemente",
                  "Sonderanfertigungen", "Zubehör"]
#: Number block and article count per product group. MOD-1042 is a moulded part.
GROUP_NUMBERS = {
    "Standardmodule": (2010, 10),
    "Formteile": (1040, 8),
    "Verbindungselemente": (3020, 9),
    "Sonderanfertigungen": (4030, 6),
    "Zubehör": (5050, 7),
}
GROUP_LABEL = {
    "Standardmodule": "Standardmodul",
    "Formteile": "Formteil",
    "Verbindungselemente": "Verbindungselement",
    "Sonderanfertigungen": "Sonderanfertigung",
    "Zubehör": "Zubehörteil",
}
#: Share of the order lines per product group.
GROUP_SHARE = {
    "Standardmodule": 0.55, "Formteile": 0.15, "Verbindungselemente": 0.15,
    "Sonderanfertigungen": 0.05, "Zubehör": 0.10,
}
GROUP_COMPLAINT_FACTOR = {
    "Standardmodule": 0.92, "Formteile": 1.10, "Verbindungselemente": 0.85,
    "Sonderanfertigungen": 2.30, "Zubehör": 0.95,
}

REASON_FIELDS = [
    "complaint_lines_reason_dimension",
    "complaint_lines_reason_surface",
    "complaint_lines_reason_material",
    "complaint_lines_reason_transport",
    "complaint_lines_reason_wrong_item",
    "complaint_lines_reason_other",
]
REASON_SHARE = {
    "Standardmodule":      [0.22, 0.20, 0.18, 0.18, 0.12, 0.10],
    "Formteile":           [0.26, 0.22, 0.18, 0.14, 0.10, 0.10],
    "Verbindungselemente": [0.24, 0.16, 0.20, 0.14, 0.16, 0.10],
    "Sonderanfertigungen": [0.34, 0.18, 0.16, 0.12, 0.08, 0.12],
    "Zubehör":             [0.14, 0.18, 0.16, 0.22, 0.20, 0.10],
}

# --------------------------------------------------------------------------- #
# Deterministic randomness
# --------------------------------------------------------------------------- #


def rng_for(seed: int, *parts: object) -> random.Random:
    """A random generator bound to the content of one row.

    Seeding from the key instead of from the call order keeps every value stable
    when the generator is refactored, and keeps the noise identical between the run
    with and the run without the planted deviations.
    """
    key = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.blake2b(key, digest_size=8).digest()
    return random.Random(seed ^ int.from_bytes(digest, "big"))


class Jitter:
    """Multiplicative noise. The flat variant draws nothing and returns 1.0."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng

    def factor(self, sigma: float, low: float = 0.5, high: float = 1.5) -> float:
        if self.rng is None:
            return 1.0
        return min(high, max(low, self.rng.gauss(1.0, sigma)))


def allocate(total: int, weights: list[float]) -> list[int]:
    """Split an integer total over weights, largest remainder method (exact sum)."""
    if total <= 0:
        return [0] * len(weights)
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return [0] * len(weights)
    raw = [total * weight / weight_sum for weight in weights]
    out = [int(value) for value in raw]
    rest = total - sum(out)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - out[i]), i))
    for index in order[:rest]:
        out[index] += 1
    return out


def allocate_capped(total: int, weights: list[float], caps: list[int]) -> list[int]:
    """Largest remainder allocation that never exceeds a per-cell cap."""
    size = len(weights)
    out = [0] * size
    active = [i for i in range(size) if caps[i] > 0 and weights[i] > 0]
    remaining = min(total, sum(caps))
    for _ in range(20):
        if remaining <= 0 or not active:
            break
        part = allocate(remaining, [weights[i] for i in active])
        overflow = 0
        still_active = []
        for position, index in enumerate(active):
            value = out[index] + part[position]
            if value >= caps[index]:
                overflow += value - caps[index]
                out[index] = caps[index]
            else:
                out[index] = value
                still_active.append(index)
        active = still_active
        remaining = overflow
    return out


def block_of(week: int) -> int:
    """Four-week block index 0..12 of a calendar week."""
    return (week - 1) // 4


def period_of(week: int) -> int:
    """Four-week period 1..13 of a calendar week (decision OP-1)."""
    return (week - 1) // ASSORTMENT_PERIOD_WEEKS + 1


# --------------------------------------------------------------------------- #
# Article master data
# --------------------------------------------------------------------------- #


def build_articles(seed: int) -> list[dict]:
    """40 neutral demo articles in five product groups, each with a popularity."""
    articles: list[dict] = []
    for group in PRODUCT_GROUPS:
        first_number, count = GROUP_NUMBERS[group]
        for index in range(count):
            article_id = f"MOD-{first_number + index}"
            rng = rng_for(seed, "article", article_id)
            articles.append({
                "article_id": article_id,
                "article_label": f"{GROUP_LABEL[group]} {index + 1:02d}",
                "product_group": group,
                "popularity": round(min(1.9, max(0.45, rng.lognormvariate(0.0, 0.30))), 4),
                "complaint_factor": round(min(1.25, max(0.80, rng.gauss(1.0, 0.08))), 4),
            })
    return articles


# --------------------------------------------------------------------------- #
# Dimension combinations of the fact table
# --------------------------------------------------------------------------- #


def fact_keys() -> list[tuple[str, str, str, float]]:
    """Every (market, channel, partner) combination with its share of the inquiries."""
    keys: list[tuple[str, str, str, float]] = []
    for market in MARKETS:
        for channel in CHANNELS:
            mix = CHANNEL_MIX[market].get(channel)
            if not mix:
                continue
            keys.append((market, channel, PARTNER_OF_MARKET[market], MARKET_SHARE[market] * mix))
    return keys


FACT_COLUMNS = [
    "week", "market", "channel", "partner",
    "inquiries_received", "quotes_sent", "quotes_decided", "quotes_won",
    "orders_placed", "orders_shipped", "orders_delivered", "orders_otif",
    "lines_shipped", "lines_complained", "complaints_closed",
    "delivery_inquiries", "key_accounts_assigned", "key_accounts_active",
    "stage1_inquiry_to_quote_hours", "stage2_quote_to_order_hours",
    "stage3_order_entry_hours", "stage4_production_shipping_hours",
    "stage5_complaint_hours",
    "revenue_eur", "revenue_prior_year_eur", "contribution_margin_eur",
    "quote_cost_eur", "complaint_cost_eur", "service_cost_eur",
]


def no_growth_factor(market: str, week: int, anomalies: bool) -> float:
    """Planted deviation 4: demand in NO grows from KW 20 beyond the plan."""
    if not anomalies or market != NO_MARKET or week < NO_GROWTH_START:
        return 1.0
    return min(NO_GROWTH_MAX, 1.0 + NO_GROWTH_STEP * (week - NO_GROWTH_START + 1))


def win_rate(market: str, channel: str, week: int, anomalies: bool) -> float:
    """Planted deviation 1: the quote success rate in SE breaks in from KW 32."""
    base = WIN_RATE[channel] * WIN_MARKET_FACTOR[market]
    if not anomalies or market != SE_MARKET or week < SE_WIN_START:
        return base
    market_base = sum(WIN_RATE[name] * share for name, share in CHANNEL_MIX[market].items())
    target = SE_WIN_RATE.get(week, SE_WIN_RATE_STEADY)
    return base * target / (market_base * WIN_MARKET_FACTOR[market])


def quote_extra_hours(market: str, week: int, anomalies: bool) -> float:
    """Planted deviations 2 and 4: longer quote lead time in SE and later in NO."""
    if not anomalies:
        return 0.0
    if market == SE_MARKET and week >= SE_QUOTE_START:
        return SE_QUOTE_EXTRA_HOURS.get(week, SE_QUOTE_EXTRA_HOURS_STEADY)
    if market == NO_MARKET and week >= NO_BOTTLENECK_START:
        return NO_QUOTE_EXTRA_HOURS.get(week, NO_QUOTE_EXTRA_HOURS_STEADY)
    return 0.0


def activity_rate(market: str, channel: str, week: int, anomalies: bool) -> float:
    """Planted deviation 4: the agency in NO loses touch with its key accounts."""
    base = ACTIVITY_RATE[channel]
    if not anomalies or market != NO_MARKET or week < NO_ACTIVITY_DRIFT_START:
        return base
    if week >= NO_BOTTLENECK_START:
        return base * NO_ACTIVITY.get(week, NO_ACTIVITY_STEADY) / ACTIVITY_RATE["agency"]
    return base - NO_ACTIVITY_DRIFT_PER_WEEK * (week - NO_ACTIVITY_DRIFT_START + 1)


def otif_rate(market: str, week: int, anomalies: bool) -> float:
    """Planted deviation 5: on-time-in-full in PL, KW 5-13, fixed from KW 14."""
    base = ON_TIME_IN_FULL[market]
    if not anomalies or market != PL_MARKET:
        return base
    if week in PL_OTIF:
        return PL_OTIF[week]
    if week >= PL_OTIF_FIXED_FROM:
        return PL_OTIF_AFTER
    return base


# --------------------------------------------------------------------------- #
# Fact table
# --------------------------------------------------------------------------- #


def build_facts(seed: int, anomalies: bool, noise: bool) -> list[dict]:
    """The weekly fact table.

    Every planted deviation is a deterministic multiplier applied after the
    random draws, so the control dataset carries the identical noise. The
    prior-year revenue is derived from the undisturbed path of the same row: a
    prior year does not change because this year a competitor enters a market.
    """
    rows: list[dict] = []
    for week in range(1, WEEKS + 1):
        week_jitter = Jitter(rng_for(seed, "week", week) if noise else None)
        week_factor = SEASON[week - 1] * week_jitter.factor(0.025, 0.92, 1.08)
        for market, channel, partner, share in fact_keys():
            jitter = Jitter(rng_for(seed, "facts", week, market, channel) if noise else None)
            demand = BASE_INQUIRIES_PER_WEEK * share * week_factor * jitter.factor(0.050, 0.82, 1.18)

            def funnel(growth: float, rate_won: float) -> tuple[int, int, int, int]:
                inquiries = round(demand * growth)
                sent = round(inquiries * QUOTE_RATE[channel])
                decided = round(sent * DECISION_RATE)
                won = round(decided * rate_won)
                return inquiries, sent, decided, won

            noise_win = jitter.factor(0.045, 0.85, 1.15)
            inquiries, quotes_sent, quotes_decided, quotes_won = funnel(
                no_growth_factor(market, week, anomalies),
                min(0.95, win_rate(market, channel, week, anomalies) * noise_win))
            _, _, _, won_plan = funnel(1.0, min(0.95, win_rate(market, channel, week, False) * noise_win))

            orders_placed = quotes_won
            orders_shipped = min(orders_placed, round(orders_placed * ORDER_SHIP_RATE
                                                      * jitter.factor(0.006, 0.96, 1.02)))
            orders_delivered = min(orders_shipped, round(orders_shipped * DELIVERED_SHARE))
            rate_otif = otif_rate(market, week, anomalies) * jitter.factor(0.012, 0.94, 1.05)
            orders_otif = min(orders_delivered, round(orders_delivered * min(0.995, rate_otif)))

            lines_shipped = round(orders_shipped * LINES_PER_ORDER * jitter.factor(0.030, 0.88, 1.12))
            complaint = (COMPLAINT_RATE * COMPLAINT_MARKET_FACTOR[market]
                         * jitter.factor(0.120, 0.60, 1.40))
            lines_complained = min(lines_shipped, round(lines_shipped * complaint))
            complaints_closed = round(lines_complained * COMPLAINT_CLOSED_SHARE
                                      * jitter.factor(0.020, 0.92, 1.05))

            inquiry_rate = (DELIVERY_INQUIRIES[channel] * DELIVERY_INQUIRY_MARKET_FACTOR[market]
                            * jitter.factor(0.080, 0.75, 1.25))
            delivery_inquiries = round(orders_placed * inquiry_rate / 100.0)

            accounts = round(KEY_ACCOUNTS * share)
            accounts_active = min(accounts, round(
                accounts * min(0.99, activity_rate(market, channel, week, anomalies)
                               * jitter.factor(0.015, 0.94, 1.05))))

            stage1 = ((STAGE1_INQUIRY_TO_QUOTE[channel] + quote_extra_hours(market, week, anomalies))
                      * jitter.factor(0.050, 0.85, 1.15))
            stage2 = STAGE2_QUOTE_TO_ORDER[channel] * jitter.factor(0.050, 0.85, 1.15)
            stage3 = STAGE3_ORDER_ENTRY[channel] * jitter.factor(0.060, 0.80, 1.20)
            stage4 = STAGE4_PRODUCTION_SHIPPING[market] * jitter.factor(0.035, 0.88, 1.12)
            stage5 = STAGE5_COMPLAINT[channel] * jitter.factor(0.070, 0.80, 1.20)

            order_value = REVENUE_PER_ORDER * PRICE_LEVEL[market] * jitter.factor(0.040, 0.88, 1.12)
            margin = MARGIN_RATE[channel] * jitter.factor(0.025, 0.92, 1.08)
            plan_shipped = won_plan * ORDER_SHIP_RATE
            prior_year = (plan_shipped * REVENUE_PER_ORDER * PRICE_LEVEL[market]
                          / MARKET_GROWTH[market] * jitter.factor(0.030, 0.90, 1.10))

            rows.append({
                "week": week,
                "market": market,
                "channel": channel,
                "partner": partner,
                "inquiries_received": inquiries,
                "quotes_sent": quotes_sent,
                "quotes_decided": quotes_decided,
                "quotes_won": quotes_won,
                "orders_placed": orders_placed,
                "orders_shipped": orders_shipped,
                "orders_delivered": orders_delivered,
                "orders_otif": orders_otif,
                "lines_shipped": lines_shipped,
                "lines_complained": lines_complained,
                "complaints_closed": complaints_closed,
                "delivery_inquiries": delivery_inquiries,
                "key_accounts_assigned": accounts,
                "key_accounts_active": accounts_active,
                "stage1_inquiry_to_quote_hours": quotes_sent * stage1,
                "stage2_quote_to_order_hours": quotes_won * stage2,
                "stage3_order_entry_hours": orders_shipped * stage3,
                "stage4_production_shipping_hours": orders_shipped * stage4,
                "stage5_complaint_hours": complaints_closed * stage5,
                "revenue_eur": orders_shipped * order_value,
                "revenue_prior_year_eur": prior_year,
                "contribution_margin_eur": orders_shipped * order_value * margin,
                "quote_cost_eur": quotes_sent * QUOTE_COST[channel],
                "complaint_cost_eur": complaints_closed * COMPLAINT_COST_PER_LINE,
                "service_cost_eur": delivery_inquiries * SERVICE_COST_PER_INQUIRY,
            })
    return rows


# --------------------------------------------------------------------------- #
# Assortment table
# --------------------------------------------------------------------------- #

ASSORTMENT_MEASURES = [
    "lines_shipped",
    "lines_complained",
    *REASON_FIELDS,
]


def article_complaint_rate(article: dict, week: int, anomalies: bool) -> float:
    """Complaint propensity of one article; planted deviation 3 lives here."""
    if (anomalies and article["article_id"] == ARTICLE_ISSUE_ID
            and week >= ARTICLE_ISSUE_START_WEEK):
        return ARTICLE_ISSUE_COMPLAINT_RATE
    return COMPLAINT_RATE * GROUP_COMPLAINT_FACTOR[article["product_group"]] * article["complaint_factor"]


def build_assortment(seed: int, facts: list[dict], articles: list[dict], anomalies: bool,
                     period_weeks: int) -> list[dict]:
    """Article rows, derived from the weekly totals of the fact table.

    The totals come from ``facts_weekly``, so both tables report the same order
    lines and the same complaints per week by construction (consistency condition
    in section 7.2 of the KPI catalogue).
    """
    lines_per_week: dict[int, int] = {week: 0 for week in range(1, WEEKS + 1)}
    complaints_per_week: dict[int, int] = {week: 0 for week in range(1, WEEKS + 1)}
    for row in facts:
        lines_per_week[row["week"]] += row["lines_shipped"]
        complaints_per_week[row["week"]] += row["lines_complained"]

    group_popularity = {group: sum(article["popularity"] for article in articles
                                   if article["product_group"] == group)
                        for group in PRODUCT_GROUPS}

    weekly: dict[tuple[int, str], dict[str, int]] = {}
    for week in range(1, WEEKS + 1):
        demand_weights = []
        for article in articles:
            rng = rng_for(seed, "assortment", week, article["article_id"])
            demand_weights.append(GROUP_SHARE[article["product_group"]] * article["popularity"]
                                  / group_popularity[article["product_group"]]
                                  * min(1.3, max(0.7, rng.gauss(1.0, 0.10))))
        lines = allocate(lines_per_week[week], demand_weights)

        complaint_weights = [lines[position] * article_complaint_rate(article, week, anomalies)
                             for position, article in enumerate(articles)]
        complaints = allocate_capped(complaints_per_week[week], complaint_weights, lines)

        for position, article in enumerate(articles):
            article_id = article["article_id"]
            if (anomalies and article_id == ARTICLE_ISSUE_ID
                    and week >= ARTICLE_ISSUE_START_WEEK):
                shares = [ARTICLE_ISSUE_REASONS[field] for field in REASON_FIELDS]
            else:
                shares = REASON_SHARE[article["product_group"]]
            reasons = allocate(complaints[position], shares)
            record = {
                "lines_shipped": lines[position],
                "lines_complained": complaints[position],
            }
            for field, value in zip(REASON_FIELDS, reasons):
                record[field] = value
            weekly[(week, article_id)] = record

    # Condense to four-week periods when required by decision OP-1.
    grouped: dict[tuple[int, str], dict[str, int]] = {}
    for (week, article_id), record in weekly.items():
        bucket = week if period_weeks == 1 else (week - 1) // period_weeks + 1
        target = grouped.setdefault((bucket, article_id),
                                    {field: 0 for field in ASSORTMENT_MEASURES})
        for field in ASSORTMENT_MEASURES:
            target[field] += record[field]

    group_of = {article["article_id"]: article["product_group"] for article in articles}
    key_name = "week" if period_weeks == 1 else "period"
    rows = []
    for (bucket, article_id) in sorted(grouped):
        record = grouped[(bucket, article_id)]
        row = {key_name: bucket, "product_group": group_of[article_id], "article_id": article_id}
        row.update({field: record[field] for field in ASSORTMENT_MEASURES})
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Capacity table
# --------------------------------------------------------------------------- #

CAPACITY_COLUMNS = [
    "week", "partner",
    "capacity_quotes_contracted", "capacity_quotes_flex", "quotes_processed",
    "staff_hours_planned", "staff_hours_worked",
]


def processed_per_partner(facts: list[dict]) -> dict[tuple[int, str], int]:
    """Quotes processed = quotes sent by the sales organisation of the partner."""
    processed: dict[tuple[int, str], int] = {}
    for row in facts:
        key = (row["week"], row["partner"])
        processed[key] = processed.get(key, 0) + row["quotes_sent"]
    return processed


def build_capacity(seed: int, facts: list[dict], forecast_facts: list[dict]) -> list[dict]:
    """Weekly quote capacity planned from the sales forecast, plus what was processed.

    ``forecast_facts`` is the run without the planted deviations: staffing is
    planned on the forecast volume and therefore carries the same figures in the
    dataset with and without the deviations -- a sales team does not grow because a
    market runs hot. The forecast itself is off by a few percent each week, which is
    why the utilisation moves around the planning level of 80 percent.
    """
    actual = processed_per_partner(facts)
    planned = processed_per_partner(forecast_facts)
    rows = []
    for week in range(1, WEEKS + 1):
        for partner in CAPACITY_PARTNERS:
            rng = rng_for(seed, "capacity", week, partner)
            forecast_error = min(1.06, max(0.94, rng.gauss(1.0, 0.030)))
            raw = planned[(week, partner)] * forecast_error / PLANNING_UTILISATION
            contracted = int(round(raw / CAPACITY_ROUNDING) * CAPACITY_ROUNDING)
            flex = int(round(contracted * CAPACITY_FLEX_SHARE / CAPACITY_ROUNDING) * CAPACITY_ROUNDING)
            quotes_processed = actual[(week, partner)]
            productivity = QUOTES_PER_STAFF_HOUR[partner]
            utilisation = quotes_processed / contracted if contracted else 0.0
            efficiency = 1.0 - max(0.0, utilisation - 0.85) * 0.60
            rows.append({
                "week": week,
                "partner": partner,
                "capacity_quotes_contracted": contracted,
                "capacity_quotes_flex": flex,
                "quotes_processed": quotes_processed,
                "staff_hours_planned": planned[(week, partner)] / productivity,
                "staff_hours_worked": quotes_processed / (productivity * efficiency),
            })
    return rows


# --------------------------------------------------------------------------- #
# Order sample (display only -- no KPI is ever computed from it, rule F4)
# --------------------------------------------------------------------------- #

ORDERS_SAMPLE_COLUMNS = [
    "order_id", "week", "market", "channel", "partner",
    "product_group", "article_id", "lines",
    "h_stage1", "h_stage2", "h_stage3", "h_stage4", "h_stage5",
    "otif", "complained", "complaint_reason", "delivery_inquiry",
    "order_value_eur", "contribution_margin_eur",
]


def pick_weighted(rng: random.Random, items: list, weights: list[float]):
    """Deterministic weighted pick without random.choices (stable across versions)."""
    total = sum(weights)
    if total <= 0:
        return items[0]
    threshold = rng.random() * total
    cumulative = 0.0
    for item, weight in zip(items, weights):
        cumulative += weight
        if threshold <= cumulative:
            return item
    return items[-1]


def build_orders_sample(seed: int, facts: list[dict], assortment: list[dict], articles: list[dict],
                        period_weeks: int) -> list[dict]:
    """Roughly 3.000 single orders, drawn evenly over the 52 weeks."""
    by_week: dict[int, list[dict]] = {}
    for row in facts:
        by_week.setdefault(row["week"], []).append(row)

    key_name = "week" if period_weeks == 1 else "period"
    items_by_bucket: dict[int, list[tuple[str, str, int]]] = {}
    for row in assortment:
        bucket = row[key_name]
        if row["lines_shipped"] > 0:
            items_by_bucket.setdefault(bucket, []).append(
                (row["product_group"], row["article_id"], row["lines_shipped"]))

    per_week = ORDERS_SAMPLE_SIZE // WEEKS
    extra = ORDERS_SAMPLE_SIZE - per_week * WEEKS

    rows = []
    counter = 0
    for week in range(1, WEEKS + 1):
        count = per_week + (1 if week <= extra else 0)
        fact_rows = by_week[week]
        fact_weights = [row["orders_placed"] for row in fact_rows]
        bucket = week if period_weeks == 1 else (week - 1) // period_weeks + 1
        items = items_by_bucket.get(bucket, [])
        item_weights = [entry[2] for entry in items]
        for index in range(count):
            counter += 1
            rng = rng_for(seed, "order", counter)
            fact = pick_weighted(rng, fact_rows, fact_weights)
            group, article_id, _ = pick_weighted(rng, items, item_weights)
            sent = max(1, fact["quotes_sent"])
            won = max(1, fact["quotes_won"])
            shipped = max(1, fact["orders_shipped"])
            delivered = max(1, fact["orders_delivered"])
            closed = max(1, fact["complaints_closed"])

            lines = max(1, round(LINES_PER_ORDER * min(2.5, max(0.2, rng.lognormvariate(0, 0.45)))))
            h1 = fact["stage1_inquiry_to_quote_hours"] / sent * min(2.5, max(0.3, rng.lognormvariate(0, 0.35)))
            h2 = fact["stage2_quote_to_order_hours"] / won * min(2.5, max(0.3, rng.lognormvariate(0, 0.30)))
            h3 = fact["stage3_order_entry_hours"] / shipped * min(2.5, max(0.3, rng.lognormvariate(0, 0.30)))
            h4 = fact["stage4_production_shipping_hours"] / shipped * min(2.5, max(0.3, rng.lognormvariate(0, 0.25)))

            otif = 1 if rng.random() < fact["orders_otif"] / delivered else 0
            complaint_probability = fact["lines_complained"] / max(1, fact["lines_shipped"]) * lines
            complained = 1 if rng.random() < min(0.9, complaint_probability) else 0
            if complained:
                reason = pick_weighted(rng, REASON_FIELDS, list(REASON_SHARE[group]))
                h5 = fact["stage5_complaint_hours"] / closed * min(2.5, max(0.3, rng.lognormvariate(0, 0.30)))
            else:
                reason = ""
                h5 = 0.0
            inquiry = 1 if rng.random() < fact["delivery_inquiries"] / max(1, fact["orders_placed"]) else 0
            value = fact["revenue_eur"] / shipped * min(2.5, max(0.3, rng.lognormvariate(0, 0.40)))
            margin = value * fact["contribution_margin_eur"] / max(1.0, fact["revenue_eur"])

            rows.append({
                "order_id": f"AUF-{counter:06d}",
                "week": week,
                "market": fact["market"],
                "channel": fact["channel"],
                "partner": fact["partner"],
                "product_group": group,
                "article_id": article_id,
                "lines": lines,
                "h_stage1": h1,
                "h_stage2": h2,
                "h_stage3": h3,
                "h_stage4": h4,
                "h_stage5": h5,
                "otif": otif,
                "complained": complained,
                "complaint_reason": reason,
                "delivery_inquiry": inquiry,
                "order_value_eur": value,
                "contribution_margin_eur": margin,
            })
    return rows


# --------------------------------------------------------------------------- #
# Parameter block (KPI catalogue 7.5, decisions OP-5 and A6)
# --------------------------------------------------------------------------- #


def build_parameters(capacity: list[dict]) -> dict:
    nordic = [row["capacity_quotes_contracted"] for row in capacity
              if row["partner"] in NORDIC_AGENCIES]
    mean_nordic = sum(nordic) / len(nordic) * len(NORDIC_AGENCIES)
    # Decision OP-5: a subsidiary of its own takes over 50 % of the Nordic quote
    # volume and brings 80 % of the combined agency capacity on top.
    subsidiary_capacity = int(round(mean_nordic * 0.80 / 10) * 10)
    return {
        "minutes_per_delivery_inquiry": 9.0,
        "minutes_per_complaint": 95.0,
        "price_concession_share": 0.05,
        "subsidiary_capacity_quotes_per_week": subsidiary_capacity,
        "subsidiary_volume_share": 0.50,
        "subsidiary_source_partners": list(NORDIC_AGENCIES),
        "subsidiary_setup_cost_eur": 1400000,
        "subsidiary_running_cost_eur_per_year": 950000,
        "min_denominator": 50,
        "min_denominator_item": 30,
        "baseline_weeks": 8,
        "zscore_threshold": 2.5,
        "consecutive_weeks": 2,
    }


#: Agencies whose volume an own Nordic subsidiary would take over.
NORDIC_AGENCIES = ("partner_4", "partner_5")


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #


def as_table(columns: list[str], rows: list[dict]) -> dict:
    """Column header plus row arrays (NFR-05), with every float rounded."""
    packed = []
    for row in rows:
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                value = round(value, FLOAT_DECIMALS)
            values.append(value)
        packed.append(values)
    return {"columns": columns, "rows": packed}


def build_dataset(seed: int, anomalies: bool, period_weeks: int) -> dict:
    articles = build_articles(seed)
    facts = build_facts(seed, anomalies=anomalies, noise=True)
    forecast_facts = facts if not anomalies else build_facts(seed, anomalies=False, noise=True)
    assortment = build_assortment(seed, facts, articles, anomalies, period_weeks)
    capacity = build_capacity(seed, facts, forecast_facts)
    orders = build_orders_sample(seed, facts, assortment, articles, period_weeks)
    parameters = build_parameters(capacity)

    key_name = "week" if period_weeks == 1 else "period"
    assortment_columns = [key_name, "product_group", "article_id", *ASSORTMENT_MEASURES]

    return {
        "meta": {
            "weeks": WEEKS,
            "seed": seed,
            "anomalies": anomalies,
            "assortment_grain": key_name,
            "assortment_period_weeks": period_weeks,
            "float_decimals": FLOAT_DECIMALS,
            "currency": "EUR",
            "note": "Synthetischer Demo-Datensatz, ausschliesslich additive Messgroessen.",
        },
        "parameters": parameters,
        "articles": as_table(["article_id", "article_label", "product_group"], articles),
        "facts_weekly": as_table(FACT_COLUMNS, facts),
        "assortment_periods": as_table(assortment_columns, assortment),
        "capacity_weekly": as_table(CAPACITY_COLUMNS, capacity),
        "orders_sample": as_table(ORDERS_SAMPLE_COLUMNS, orders),
    }


def write_dataset(dataset: dict, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dataset, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8", newline="\n")
    return len(text.encode("utf-8"))


# --------------------------------------------------------------------------- #
# Self-check: consistency conditions of the KPI catalogue, section 7
# --------------------------------------------------------------------------- #


def records(table: dict) -> list[dict]:
    """Row arrays back into dictionaries -- used by the checks and the printouts."""
    columns = table["columns"]
    return [dict(zip(columns, row)) for row in table["rows"]]


def check_dataset(dataset: dict) -> list[str]:
    """Every consistency condition from section 7 of the KPI catalogue."""
    problems: list[str] = []
    facts = records(dataset["facts_weekly"])
    assortment = records(dataset["assortment_periods"])
    capacity = records(dataset["capacity_weekly"])
    period_weeks = dataset["meta"]["assortment_period_weeks"]
    key_name = dataset["meta"]["assortment_grain"]

    def fail(message: str) -> None:
        if len(problems) < 25:
            problems.append(message)

    ordered_pairs = [
        ("quotes_sent", "inquiries_received"),
        ("quotes_decided", "quotes_sent"),
        ("quotes_won", "quotes_decided"),
        ("orders_shipped", "orders_placed"),
        ("orders_delivered", "orders_shipped"),
        ("orders_otif", "orders_delivered"),
        ("lines_complained", "lines_shipped"),
        ("key_accounts_active", "key_accounts_assigned"),
    ]

    # -- facts_weekly ------------------------------------------------------
    for row in facts:
        where = f"facts KW {row['week']} {row['market']}/{row['channel']}"
        for field, value in row.items():
            if isinstance(value, (int, float)) and value < 0:
                fail(f"{where}: {field} ist negativ")
        for smaller, larger in ordered_pairs:
            if row[smaller] > row[larger]:
                fail(f"{where}: {smaller} > {larger}")
        if row["partner"] != PARTNER_OF_MARKET[row["market"]]:
            fail(f"{where}: Partner {row['partner']} passt nicht zum Markt")
        if row["channel"] not in CHANNEL_MIX[row["market"]]:
            fail(f"{where}: Vertriebsweg {row['channel']} gibt es in diesem Markt nicht")

    # -- assortment_periods -------------------------------------------------
    for row in assortment:
        where = f"assortment {key_name} {row[key_name]} {row['article_id']}"
        reason_sum = sum(row[field] for field in REASON_FIELDS)
        if reason_sum != row["lines_complained"]:
            fail(f"{where}: Summe der Gruende {reason_sum} != lines_complained {row['lines_complained']}")
        if row["lines_complained"] > row["lines_shipped"]:
            fail(f"{where}: lines_complained > lines_shipped")

    facts_lines: dict[int, int] = {}
    facts_complaints: dict[int, int] = {}
    for row in facts:
        bucket = row["week"] if period_weeks == 1 else (row["week"] - 1) // period_weeks + 1
        facts_lines[bucket] = facts_lines.get(bucket, 0) + row["lines_shipped"]
        facts_complaints[bucket] = facts_complaints.get(bucket, 0) + row["lines_complained"]
    assortment_lines: dict[int, int] = {}
    assortment_complaints: dict[int, int] = {}
    for row in assortment:
        bucket = row[key_name]
        assortment_lines[bucket] = assortment_lines.get(bucket, 0) + row["lines_shipped"]
        assortment_complaints[bucket] = assortment_complaints.get(bucket, 0) + row["lines_complained"]
    for bucket in sorted(facts_lines):
        if facts_lines[bucket] != assortment_lines.get(bucket, 0):
            fail(f"{key_name} {bucket}: lines_shipped {facts_lines[bucket]} != "
                 f"{assortment_lines.get(bucket, 0)} im Sortiment")
        if facts_complaints[bucket] != assortment_complaints.get(bucket, 0):
            fail(f"{key_name} {bucket}: lines_complained {facts_complaints[bucket]} != "
                 f"{assortment_complaints.get(bucket, 0)} im Sortiment")

    # -- capacity_weekly ---------------------------------------------------
    expected = processed_per_partner(facts)
    for row in capacity:
        key = (row["week"], row["partner"])
        if row["quotes_processed"] != expected.get(key, 0):
            fail(f"capacity KW {row['week']} {row['partner']}: quotes_processed "
                 f"{row['quotes_processed']} != {expected.get(key, 0)} aus facts_weekly")
        if row["capacity_quotes_contracted"] <= 0:
            fail(f"capacity KW {row['week']} {row['partner']}: keine Kapazitaet")
    partners_in_capacity = {row["partner"] for row in capacity}
    if partners_in_capacity != set(CAPACITY_PARTNERS):
        fail(f"capacity_weekly enthaelt {sorted(partners_in_capacity)}, erwartet {CAPACITY_PARTNERS}")

    # -- table shape (NFR-05) ---------------------------------------------
    for name in ("facts_weekly", "assortment_periods", "capacity_weekly", "orders_sample", "articles"):
        table = dataset[name]
        if set(table) != {"columns", "rows"}:
            fail(f"{name}: erwartet wird {{columns, rows}} (NFR-05)")
            continue
        width = len(table["columns"])
        if any(len(row) != width for row in table["rows"]):
            fail(f"{name}: Zeile mit abweichender Spaltenzahl")
    return problems


# --------------------------------------------------------------------------- #
# Self-check: the ten mandatory KPIs over the whole dataset
# --------------------------------------------------------------------------- #

KPI_LABELS = [
    ("quote_lead_time_h", "Angebotsdurchlaufzeit", "h", "<= 24,0"),
    ("quote_win_rate", "Angebotserfolgsquote", "%", ">= 32,0"),
    ("order_lead_time_d", "Auftragsdurchlaufzeit", "d", "<= 9,0"),
    ("otif_rate", "Liefertreue (Termin und Menge)", "%", ">= 95,0"),
    ("complaint_rate_lines", "Reklamationsquote (Positionen)", "%", "<= 1,20"),
    ("complaint_processing_time_d", "Reklamationsbearbeitungszeit", "d", "<= 5,0"),
    ("delivery_inquiries_per_100_orders", "Lieferterminanfragen je 100 Auftr.", "je 100", "<= 12,0"),
    ("contribution_margin_per_order_eur", "Deckungsbeitrag je Auftrag", "EUR", ">= 1.150"),
    ("revenue_index", "Umsatzindex zur Vorjahresbasis", "Index", ">= 100"),
    ("partner_activity_rate", "Aktivitaetsgrad der Vertretungen", "%", ">= 85,0"),
]


def total(rows: list[dict], field: str) -> float:
    return sum(row[field] for row in rows)


def headline_kpis(dataset: dict) -> dict[str, float]:
    facts = records(dataset["facts_weekly"])
    return {
        "quote_lead_time_h": total(facts, "stage1_inquiry_to_quote_hours") / total(facts, "quotes_sent"),
        "quote_win_rate": total(facts, "quotes_won") / total(facts, "quotes_decided") * 100,
        "order_lead_time_d": (total(facts, "stage3_order_entry_hours")
                              + total(facts, "stage4_production_shipping_hours"))
        / 24 / total(facts, "orders_shipped"),
        "otif_rate": total(facts, "orders_otif") / total(facts, "orders_delivered") * 100,
        "complaint_rate_lines": total(facts, "lines_complained") / total(facts, "lines_shipped") * 100,
        "complaint_processing_time_d": total(facts, "stage5_complaint_hours") / 24
        / total(facts, "complaints_closed"),
        "delivery_inquiries_per_100_orders": total(facts, "delivery_inquiries")
        / total(facts, "orders_placed") * 100,
        "contribution_margin_per_order_eur": total(facts, "contribution_margin_eur")
        / total(facts, "orders_shipped"),
        "revenue_index": total(facts, "revenue_eur") / total(facts, "revenue_prior_year_eur") * 100,
        "partner_activity_rate": total(facts, "key_accounts_active")
        / total(facts, "key_accounts_assigned") * 100,
    }


def print_kpis(dataset: dict) -> None:
    values = headline_kpis(dataset)
    print("Pflichtkennzahlen ueber den Gesamtdatensatz")
    print(f"{'Kennzahl':38} {'Wert':>10}  {'Einheit':7} {'Zielwert':>9}")
    print("-" * 70)
    for key, label, unit, target in KPI_LABELS:
        print(f"{label:38} {values[key]:10.2f}  {unit:7} {target:>9}")
    print()


# --------------------------------------------------------------------------- #
# Self-check: the planted deviations as weekly series
# --------------------------------------------------------------------------- #


def series_line(title: str, weeks: list[int], values: list[float], fmt: str = "{:.1f}") -> None:
    print(title)
    chunk = 13
    for start in range(0, len(weeks), chunk):
        head = "  KW  " + " ".join(f"{week:>6}" for week in weeks[start:start + chunk])
        body = "  Wert" + " ".join(f"{fmt.format(value):>6}" for value in values[start:start + chunk])
        print(head)
        print(body)
    print()


def market_series(facts: list[dict], market: str, numerator: str, denominator: str,
                  factor: float = 1.0) -> list[float]:
    values = []
    for week in range(1, WEEKS + 1):
        rows = [row for row in facts if row["week"] == week and row["market"] == market]
        values.append(total(rows, numerator) / total(rows, denominator) * factor
                      if total(rows, denominator) else 0.0)
    return values


def print_anomaly_series(dataset: dict) -> None:
    facts = records(dataset["facts_weekly"])
    capacity = records(dataset["capacity_weekly"])
    assortment = records(dataset["assortment_periods"])
    key_name = dataset["meta"]["assortment_grain"]
    weeks = list(range(1, WEEKS + 1))

    print("Verlauf der eingepflanzten Auffaelligkeiten")
    print("=" * 70)
    series_line("1) Angebotserfolgsquote Markt SE in Prozent", weeks,
                market_series(facts, "SE", "quotes_won", "quotes_decided", 100))
    series_line("2) Angebotsdurchlaufzeit Markt SE in Stunden", weeks,
                market_series(facts, "SE", "stage1_inquiry_to_quote_hours", "quotes_sent"))

    buckets = sorted({row[key_name] for row in assortment})
    issue, siblings = [], []
    group = next(row["product_group"] for row in assortment if row["article_id"] == ARTICLE_ISSUE_ID)
    for bucket in buckets:
        cells = [row for row in assortment
                 if row[key_name] == bucket and row["product_group"] == group]
        hit = [row for row in cells if row["article_id"] == ARTICLE_ISSUE_ID]
        rest = [row for row in cells if row["article_id"] != ARTICLE_ISSUE_ID]
        issue.append(total(hit, "lines_complained") / total(hit, "lines_shipped") * 100
                     if total(hit, "lines_shipped") else 0.0)
        siblings.append(total(rest, "lines_complained") / total(rest, "lines_shipped") * 100
                        if total(rest, "lines_shipped") else 0.0)
    label = "Periode" if key_name == "period" else "KW"
    print(f"3) Reklamationsquote {ARTICLE_ISSUE_ID} in Prozent, je {label} "
          f"(gegen die uebrigen Artikel der Gruppe {group})")
    print("  " + label.ljust(6) + " ".join(f"{bucket:>6}" for bucket in buckets))
    print("  Artik." + " ".join(f"{value:6.2f}" for value in issue))
    print("  uebr. " + " ".join(f"{value:6.2f}" for value in siblings))
    print()

    series_line("4a) Aktivitaetsgrad Markt NO in Prozent", weeks,
                market_series(facts, "NO", "key_accounts_active", "key_accounts_assigned", 100))
    series_line("4b) Angebotsdurchlaufzeit Markt NO in Stunden", weeks,
                market_series(facts, "NO", "stage1_inquiry_to_quote_hours", "quotes_sent"))
    utilisation = []
    for week in weeks:
        rows = [row for row in capacity if row["week"] == week and row["partner"] == NO_PARTNER]
        utilisation.append(total(rows, "quotes_processed") / total(rows, "capacity_quotes_contracted") * 100)
    series_line(f"4c) Auslastung der Angebotskapazitaet {NO_PARTNER} in Prozent", weeks, utilisation)
    series_line("5) Liefertreue Markt PL in Prozent", weeks,
                market_series(facts, "PL", "orders_otif", "orders_delivered", 100))


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Erzeugt den Demo-Datensatz des International Sales Cockpits.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Zielpfad (Standard data/dataset.json)")
    parser.add_argument("--seed", type=int, default=SEED, help=f"Seed (Standard {SEED})")
    parser.add_argument("--no-anomalies", action="store_true",
                        help="Kontrolldatensatz: gleiches Rauschen, ohne die fuenf Ereignisse")
    parser.add_argument("--assortment-weekly", action="store_true",
                        help="Sortimenttabelle wochenweise statt in Vier-Wochen-Perioden (Messung zu OP-1)")
    parser.add_argument("--quiet", action="store_true", help="Nur Dateigroesse und Hash ausgeben")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    anomalies = not args.no_anomalies
    period_weeks = 1 if args.assortment_weekly else ASSORTMENT_PERIOD_WEEKS
    out_path = Path(args.out)

    dataset = build_dataset(args.seed, anomalies, period_weeks)
    size = write_dataset(dataset, out_path)
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()

    problems = check_dataset(dataset)
    if not args.quiet:
        facts_rows = len(dataset["facts_weekly"]["rows"])
        print(f"Datensatz: {out_path}")
        print(f"Auffaelligkeiten eingepflanzt: {'ja' if anomalies else 'nein (Kontrolldatensatz)'}")
        print(f"Seed: {args.seed} | Sortimentraster: {dataset['meta']['assortment_grain']}")
        print(f"Zeilen: facts_weekly {facts_rows}, "
              f"assortment_periods {len(dataset['assortment_periods']['rows'])}, "
              f"capacity_weekly {len(dataset['capacity_weekly']['rows'])}, "
              f"orders_sample {len(dataset['orders_sample']['rows'])}")
        print()
        print_kpis(dataset)
        print_anomaly_series(dataset)

    print(f"Dateigroesse: {size / 1024:.1f} KB (Grenze nach OP-1: {SIZE_LIMIT_BYTES / 1024:.0f} KB)")
    if size > SIZE_LIMIT_BYTES:
        print("WARNUNG: Groessengrenze nach Entscheidung OP-1 ueberschritten.")
    print(f"SHA-256: {digest}")

    if problems:
        print()
        print(f"Konsistenzpruefung FEHLGESCHLAGEN ({len(problems)} Befunde):")
        for problem in problems:
            print("  - " + problem)
        return 1
    print("Konsistenzpruefung: alle Bedingungen aus KPI_DEFINITIONS Abschnitt 7 erfuellt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
