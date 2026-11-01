"""Deterministic randomness, money rounding, working-time arithmetic and ID formatting."""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .config import FISCAL_YEAR

WORK_START_H, WORK_END_H = 8, 18
WORK_MINUTES_PER_DAY = (WORK_END_H - WORK_START_H) * 60


# ------------------------------------------------------------------ randomness
def rng(seed: int, *keys) -> random.Random:
    """Independent, order-free random stream per entity.

    Seeding with a string goes through SHA-512 inside `random`, so the stream depends only on
    (seed, keys) - not on how many other entities were generated before it.  This keeps the
    baseline and the anomaly-injected runs aligned record-for-record.
    """
    return random.Random("|".join(str(k) for k in (seed,) + keys))


def weighted(r: random.Random, pairs):
    """Pick from [(value, weight), ...]."""
    total = sum(w for _, w in pairs)
    x = r.random() * total
    for value, w in pairs:
        x -= w
        if x < 0:
            return value
    return pairs[-1][0]


def lognormal_between(r: random.Random, median: float, sigma: float, lo: float, hi: float) -> float:
    for _ in range(50):
        v = median * math.exp(r.gauss(0, sigma))
        if lo <= v <= hi:
            return v
    return min(max(median, lo), hi)


# ------------------------------------------------------------------ money
_CENT = Decimal("0.01")


def money(x: float) -> float:
    """Round half-up to cents (avoids banker's rounding surprises in reconciliation)."""
    return float(Decimal(repr(float(x))).quantize(_CENT, rounding=ROUND_HALF_UP))


def rate6(x: float) -> float:
    return float(Decimal(repr(float(x))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


# ------------------------------------------------------------------ working time
def is_workday(d: date) -> bool:
    return d.weekday() < 5


def next_workday(d: date) -> date:
    d = d + timedelta(days=1)
    while not is_workday(d):
        d += timedelta(days=1)
    return d


def add_business_days(d: date, n: int) -> date:
    for _ in range(n):
        d = next_workday(d)
    return d


def clamp_to_work(dt: datetime) -> datetime:
    """Move a timestamp forward to the next instant inside working hours."""
    d = dt.date()
    if is_workday(d) and WORK_START_H <= dt.hour < WORK_END_H:
        return dt.replace(second=0, microsecond=0)
    if is_workday(d) and dt.hour < WORK_START_H:
        return datetime(d.year, d.month, d.day, WORK_START_H)
    nd = next_workday(d)
    return datetime(nd.year, nd.month, nd.day, WORK_START_H)


def add_work_minutes(dt: datetime, minutes: float) -> datetime:
    dt = clamp_to_work(dt)
    remaining = max(1, int(round(minutes)))
    while True:
        end = dt.replace(hour=WORK_END_H, minute=0)
        avail = int((end - dt).total_seconds() // 60)
        if remaining < avail:
            return dt + timedelta(minutes=remaining)
        remaining -= avail
        nd = next_workday(dt.date())
        dt = datetime(nd.year, nd.month, nd.day, WORK_START_H)


def add_work_hours(dt: datetime, hours: float) -> datetime:
    return add_work_minutes(dt, hours * 60)


def work_time_on(r: random.Random, d: date) -> datetime:
    """Random submission-style timestamp on day d, peaked mid-morning / early afternoon."""
    minute = int(min(WORK_MINUTES_PER_DAY - 1, max(0, r.triangular(0, WORK_MINUTES_PER_DAY, 150))))
    return datetime(d.year, d.month, d.day, WORK_START_H) + timedelta(minutes=minute)


def at(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute)


def month_key(d) -> str:
    return f"{d.year:04d}-{d.month:02d}"


# ------------------------------------------------------------------ identifiers
def pr_id(n: int) -> str:
    return f"PR-{FISCAL_YEAR}-{n:06d}"


def rfq_id(n: int) -> str:
    return f"RFQ-{FISCAL_YEAR}-{n:06d}"


def quote_id(supplier_code: str, n: int) -> str:
    return f"QUO-{supplier_code}-{FISCAL_YEAR}-{n:06d}"


def po_id(n: int) -> str:
    return f"PO-{FISCAL_YEAR}-{n:06d}"


def delivery_id(po: str, seq: int) -> str:
    return f"DEL-{po}-{seq:02d}"


def line_id(parent: str, n: int) -> str:
    return f"{parent}-L{n:02d}"


def seq_id(prefix: str, n: int, width: int = 6, year: bool = True) -> str:
    return f"{prefix}-{FISCAL_YEAR}-{n:0{width}d}" if year else f"{prefix}-{n:0{width}d}"


class EventLog:
    """Append-only lifecycle history; IDs are assigned in time order at the end."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, entity_type: str, entity_id: str, frm, to: str, ts: datetime, actor=None, reason=None) -> None:
        self.rows.append({"entity_type": entity_type, "entity_id": entity_id, "from_status": frm,
                          "to_status": to, "event_ts": ts, "actor_id": actor, "reason": reason,
                          "_seq": len(self.rows)})

    def last_status(self) -> dict:
        out = {}
        for e in sorted(self.rows, key=lambda e: (e["event_ts"], e["_seq"])):
            out[(e["entity_type"], e["entity_id"])] = (e["to_status"], e["event_ts"])
        return out


class Counter:
    """Monotonic counter for sequential IDs."""

    def __init__(self) -> None:
        self.n = 0

    def next(self) -> int:
        self.n += 1
        return self.n
