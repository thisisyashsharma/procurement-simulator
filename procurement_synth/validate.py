"""Validation of an exported dataset folder (reads the CSV files back, so it checks what ships).

Integrity checks must all pass.  Control checks are expected to fire only on the labelled
anomalies; `controls.reconcile` proves every control violation is explained by ground truth
and every ground-truth label is detected.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from . import checks_domain, controls
from .config import AS_OF
from .schema import TABLES

LABEL_WORDS = re.compile(r"(anomal|ground_truth|issue_type|is_fraud|label)", re.I)


# ------------------------------------------------------------------ loading
def _parse(value: str, typ: str):
    if value == "":
        return None
    if typ == "INTEGER":
        return int(value)
    if typ.startswith("DECIMAL"):
        return float(value)
    if typ == "BOOLEAN":
        return value == "true"
    if typ == "DATE":
        return date.fromisoformat(value)
    if typ == "TIMESTAMP":
        return datetime.fromisoformat(value)
    return value


def load(data_dir: Path) -> tuple[dict, list[dict], dict]:
    data_dir = Path(data_dir)
    tables = {}
    for t in TABLES:
        types = {c.name: c.type for c in t.cols}
        with open(data_dir / "csv" / f"{t.name}.csv", encoding="utf-8", newline="") as fh:
            tables[t.name] = [{k: _parse(v, types[k]) for k, v in row.items()} for row in csv.DictReader(fh)]
    with open(data_dir / "ground_truth" / "ground_truth.csv", encoding="utf-8", newline="") as fh:
        gt = [dict(r) for r in csv.DictReader(fh)]
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    return tables, gt, manifest


class Report:
    def __init__(self):
        self.rows = []

    def check(self, category: str, name: str, checked: int, failures: list, expected_failures: int = 0,
              note: str = "") -> None:
        self.rows.append({"category": category, "check": name, "checked": checked, "failed": len(failures),
                          "passed": len(failures) == expected_failures, "note": note,
                          "examples": [str(f) for f in failures[:3]]})

    @property
    def ok(self) -> bool:
        return all(r["passed"] for r in self.rows)


# ------------------------------------------------------------------ generic schema checks
def schema_checks(rep: Report, T: dict) -> None:
    for t in TABLES:
        rows = T[t.name]
        keys = [tuple(r[k] for k in t.pk) for r in rows]
        dup = len(keys) - len(set(keys))
        rep.check("primary_key", f"{t.name}: PK {t.pk} unique and not null", len(rows),
                  [k for k in keys if None in k] + (["duplicate keys: %d" % dup] if dup else []))
        for c in t.cols:
            vals = [r[c.name] for r in rows]
            if c.required:
                rep.check("required", f"{t.name}.{c.name} not null", len(rows), [i for i, v in enumerate(vals) if v is None])
            if c.enum:
                rep.check("enum", f"{t.name}.{c.name} in allowed values", len(rows),
                          [v for v in vals if v is not None and v not in c.enum])
            if c.pattern:
                rx = re.compile(c.pattern)
                rep.check("id_format", f"{t.name}.{c.name} matches {c.pattern}", len(rows),
                          [v for v in vals if v is not None and not rx.fullmatch(str(v))])
            if c.unique:
                present = [v for v in vals if v is not None]
                rep.check("uniqueness", f"{t.name}.{c.name} unique", len(present),
                          [v for v in set(present) if present.count(v) > 1] if len(set(present)) != len(present) else [])
            if c.fk:
                ft, fc = c.fk.split(".")
                parent = {r[fc] for r in T[ft]}
                rep.check("foreign_key", f"{t.name}.{c.name} -> {c.fk}", len(rows),
                          [v for v in vals if v is not None and v not in parent])
        for u in t.unique:
            keys = [tuple(r[k] for k in u) for r in rows]
            rep.check("uniqueness", f"{t.name}: natural key {u} unique", len(rows),
                      ["%d duplicates" % (len(keys) - len(set(keys)))] if len(keys) != len(set(keys)) else [])
    poly = {"PURCHASE_REQUEST": ("purchase_request", "pr_id"), "PURCHASE_ORDER": ("purchase_order", "po_id"),
            "APPROVAL": ("approval", "approval_id"), "RFQ": ("rfq", "rfq_id"),
            "SUPPLIER_QUOTE": ("supplier_quote", "quote_id"), "DELIVERY": ("delivery", "delivery_id")}
    ids = {k: {r[col] for r in T[tab]} for k, (tab, col) in poly.items()}
    for tab, tcol, icol in (("budget_transaction", "source_type", "source_id"),
                            ("status_event", "entity_type", "entity_id"),
                            ("exception_register", "entity_type", "entity_id")):
        rep.check("foreign_key", f"{tab}.{icol} resolves for its {tcol}", len(T[tab]),
                  [r[icol] for r in T[tab] if r[icol] not in ids[r[tcol]]])


PLANNED = {("rfq", "response_due_at")}       # deadlines may lie after the snapshot; events may not


def timestamps_before_snapshot(rep: Report, T: dict) -> None:
    bad = []
    n = 0
    for t in TABLES:
        for c in t.cols:
            if c.type == "TIMESTAMP" and (t.name, c.name) not in PLANNED:
                for r in T[t.name]:
                    if r[c.name] is not None:
                        n += 1
                        if r[c.name] > AS_OF:
                            bad.append(f"{t.name}.{c.name}={r[c.name]}")
    rep.check("date_order", f"all event timestamps <= snapshot {AS_OF} (bid deadlines excepted)", n, bad)


def sql_load(rep: Report, data_dir: Path, T: dict) -> None:
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys = ON")
    failures = []
    try:
        con.executescript((data_dir / "sql" / "schema.sql").read_text(encoding="utf-8"))
        con.executescript((data_dir / "sql" / "seed.sql").read_text(encoding="utf-8"))
        for t in TABLES:
            n = con.execute(f"SELECT COUNT(*) FROM {t.name}").fetchone()[0]
            if n != len(T[t.name]):
                failures.append(f"{t.name}: sql {n} vs csv {len(T[t.name])}")
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        failures += [f"fk violation {row}" for row in fk[:5]]
    except sqlite3.Error as exc:
        failures.append(f"sqlite error: {exc}")
    rep.check("sql", "schema.sql + seed.sql load into SQLite with FK enforcement; counts match CSV",
              len(TABLES), failures)


def json_matches_csv(rep: Report, data_dir: Path, T: dict) -> None:
    bad = []
    for t in TABLES:
        rows = json.loads((data_dir / "json" / f"{t.name}.json").read_text(encoding="utf-8"))
        if len(rows) != len(T[t.name]) or (rows and list(rows[0]) != [c.name for c in t.cols]):
            bad.append(t.name)
    rep.check("export", "JSON files have the same rows and columns as CSV", len(TABLES), bad)


def volumes(rep: Report, T: dict, manifest: dict) -> None:
    targets = manifest["targets"]
    actual = {"requesters": len(T["requester"]), "suppliers": len(T["supplier"]),
              "purchase_request": len(T["purchase_request"]), "rfq": len(T["rfq"]),
              "supplier_quote": len(T["supplier_quote"]), "purchase_order": len(T["purchase_order"])}
    tol = 0.05 if targets["purchase_request"] >= 1000 else 0.15
    for k, target in targets.items():
        if k == "purchase_order":
            ok = abs(actual[k] - target) <= tol * target
            rep.check("volume", f"{k}: {actual[k]} vs target {target} (rule outcome, tolerance {tol:.0%})", 1,
                      [] if ok else [f"{actual[k]} outside tolerance"])
        else:
            rep.check("volume", f"{k}: {actual[k]} vs target {target} (exact)", 1,
                      [] if actual[k] == target else [f"{actual[k]} != {target}"])


def ground_truth_separation(rep: Report, T: dict, gt: list[dict]) -> None:
    leaks = [f"{t.name}.{c.name}" for t in TABLES for c in t.cols if LABEL_WORDS.search(c.name)]
    rep.check("ground_truth", "no label-like columns in input tables", sum(len(t.cols) for t in TABLES), leaks)
    ref = {"PURCHASE_REQUEST": ("purchase_request", "pr_id"), "PURCHASE_ORDER": ("purchase_order", "po_id"),
           "RFQ": ("rfq", "rfq_id")}
    missing = [g["gt_id"] for g in gt if g["entity_id"] not in {r[ref[g["entity_type"]][1]] for r in T[ref[g["entity_type"]][0]]}]
    rep.check("ground_truth", "every label references an existing record", len(gt), missing)
    ids = [g["gt_id"] for g in gt]
    rep.check("ground_truth", "label ids unique", len(ids), ["dup"] if len(ids) != len(set(ids)) else [])


def run(data_dir: Path) -> Report:
    data_dir = Path(data_dir)
    T, gt, manifest = load(data_dir)
    rep = Report()
    schema_checks(rep, T)
    timestamps_before_snapshot(rep, T)
    checks_domain.run(rep, T)
    volumes(rep, T, manifest)
    ground_truth_separation(rep, T, gt)
    json_matches_csv(rep, data_dir, T)
    sql_load(rep, data_dir, T)
    controls.reconcile(rep, T, gt)
    return rep


def write_report(rep: Report, path_md: Path, path_json: Path, title: str) -> None:
    by_cat = {}
    for r in rep.rows:
        c = by_cat.setdefault(r["category"], [0, 0])
        c[0] += 1
        c[1] += 0 if r["passed"] else 1
    lines = [f"# Validation summary - {title}", "",
             f"**Result: {'PASS' if rep.ok else 'FAIL'}** - {len(rep.rows)} checks, "
             f"{sum(1 for r in rep.rows if not r['passed'])} failing.", "",
             "| Category | Checks | Failing |", "|---|---:|---:|"]
    lines += [f"| {c} | {n} | {f} |" for c, (n, f) in by_cat.items()]
    lines += ["", "## Non-trivial checks", "", "| Category | Check | Checked | Violations | Pass | Note |",
              "|---|---|---:|---:|:-:|---|"]
    for r in rep.rows:
        if r["category"] not in ("required", "enum", "id_format", "foreign_key", "uniqueness", "primary_key") or not r["passed"]:
            lines.append(f"| {r['category']} | {r['check']} | {r['checked']} | {r['failed']} | "
                         f"{'yes' if r['passed'] else '**NO**'} | {r['note']} |")
    lines += ["", f"Schema-level checks (PK, FK, required, enum, ID format, uniqueness) are counted in the "
              f"table above; the full list is in `{path_json.name}`.", ""]
    path_md.write_text("\n".join(lines), encoding="utf-8", newline="")
    path_json.write_text(json.dumps({"passed": rep.ok, "checks": rep.rows}, indent=1, default=str) + "\n",
                         encoding="utf-8", newline="")
