"""Writers for CSV, JSON and SQL seed files plus the checksummed manifest.

Outputs are byte-for-byte deterministic for a given seed and scale (no wall-clock timestamps),
which is what the reproducibility check relies on.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from . import config as C
from .schema import GROUND_TRUTH_COLUMNS, TABLE_BY_NAME, TABLES

SQL_TYPES = {"TEXT": "TEXT", "INTEGER": "INTEGER", "DATE": "DATE", "TIMESTAMP": "TIMESTAMP", "BOOLEAN": "BOOLEAN"}
GT_COLS = [c for c, _ in GROUND_TRUTH_COLUMNS]


def fmt(value, col_type: str = "TEXT") -> str:
    """Canonical text form used by CSV (and SQL literals)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        places = 6 if "12,6" in col_type else 4 if "6,4" in col_type else 2
        return f"{value:.{places}f}"
    return str(value)


def jsonable(value, col_type: str = "TEXT"):
    if isinstance(value, (datetime, date)):
        return fmt(value)
    if isinstance(value, float):
        places = 6 if "12,6" in col_type else 4 if "6,4" in col_type else 2
        return round(value, places)
    return value


def _types(table: str) -> dict:
    return {c.name: c.type for c in TABLE_BY_NAME[table].cols}


def write_csv(path: Path, rows: list[dict], cols: list[str], types: dict) -> None:
    buf = io.StringIO()
    wr = csv.writer(buf, lineterminator="\n")
    wr.writerow(cols)
    for r in rows:
        wr.writerow([fmt(r[c], types.get(c, "TEXT")) for c in cols])
    path.write_text(buf.getvalue(), encoding="utf-8", newline="")


def write_json(path: Path, rows: list[dict], cols: list[str], types: dict) -> None:
    lines = [json.dumps({c: jsonable(r[c], types.get(c, "TEXT")) for c in cols}, ensure_ascii=False) for r in rows]
    path.write_text("[\n" + ",\n".join(lines) + "\n]\n", encoding="utf-8", newline="")


# ------------------------------------------------------------------ SQL
def ddl() -> str:
    out = ["-- Procurement P2P synthetic dataset: schema (SQLite / PostgreSQL compatible)", ""]
    for t in TABLES:
        parts = []
        for c in t.cols:
            typ = SQL_TYPES.get(c.type, c.type.replace("DECIMAL", "NUMERIC"))
            parts.append(f"  {c.name} {typ}{' NOT NULL' if c.required else ''}")
        parts.append(f"  PRIMARY KEY ({', '.join(t.pk)})")
        for c in t.cols:
            if c.fk:
                ft, fc = c.fk.split(".")
                parts.append(f"  FOREIGN KEY ({c.name}) REFERENCES {ft} ({fc})")
        for u in t.unique:
            parts.append(f"  UNIQUE ({', '.join(u)})")
        for c in t.cols:
            if c.enum:
                vals = ", ".join(str(v) if isinstance(v, int) else f"'{v}'" for v in c.enum)
                parts.append(f"  CHECK ({c.name} IS NULL OR {c.name} IN ({vals}))")
        out.append(f"CREATE TABLE {t.name} (\n" + ",\n".join(parts) + "\n);\n")
    return "\n".join(out)


def sql_literal(value, col_type: str) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return fmt(value, col_type)
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    return "'" + fmt(value).replace("'", "''") + "'"


def inserts(tables: dict) -> str:
    out = ["-- Procurement P2P synthetic dataset: seed rows (parents before children)", "BEGIN;", ""]
    for t in TABLES:
        rows = tables[t.name]
        cols = [c.name for c in t.cols]
        types = _types(t.name)
        for i in range(0, len(rows), 250):
            chunk = rows[i:i + 250]
            values = ",\n".join("(" + ", ".join(sql_literal(r[c], types[c]) for c in cols) + ")" for r in chunk)
            out.append(f"INSERT INTO {t.name} ({', '.join(cols)}) VALUES\n{values};")
        out.append("")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ dataset
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(ds, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    for sub in ("csv", "json", "sql", "ground_truth"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    files = []
    for t in TABLES:
        cols, types = [c.name for c in t.cols], _types(t.name)
        rows = ds.tables[t.name]
        write_csv(out_dir / "csv" / f"{t.name}.csv", rows, cols, types)
        write_json(out_dir / "json" / f"{t.name}.json", rows, cols, types)
        files += [(f"csv/{t.name}.csv", len(rows)), (f"json/{t.name}.json", len(rows))]
    (out_dir / "sql" / "schema.sql").write_text(ddl(), encoding="utf-8", newline="")
    (out_dir / "sql" / "seed.sql").write_text(inserts(ds.tables), encoding="utf-8", newline="")
    files += [("sql/schema.sql", None), ("sql/seed.sql", sum(len(v) for v in ds.tables.values()))]
    gt = ds.ground_truth
    write_csv(out_dir / "ground_truth" / "ground_truth.csv", gt, GT_COLS, {})
    write_json(out_dir / "ground_truth" / "ground_truth.json", gt, GT_COLS, {})
    files += [("ground_truth/ground_truth.csv", len(gt)), ("ground_truth/ground_truth.json", len(gt))]
    manifest = build_manifest(ds, out_dir, files)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="")
    return manifest


def build_manifest(ds, out_dir: Path, files) -> dict:
    cfg, scale = ds.cfg, ds.cfg.scale
    counts = {k: len(v) for k, v in ds.tables.items()}
    by_type = {}
    for g in ds.ground_truth:
        by_type[g["issue_type"]] = by_type.get(g["issue_type"], 0) + 1
    return {
        "dataset": "Procure-to-pay synthetic dataset (purchase requests to supplier delivery)",
        "generator_version": C.GENERATOR_VERSION,
        "generator_command": f"python -m procurement_synth generate --scale {scale.name} --seed {cfg.seed}",
        "seed": cfg.seed,
        "scale": asdict(scale),
        "fiscal_year": C.FISCAL_YEAR,
        "as_of": C.AS_OF.isoformat(),
        "base_currency": C.BASE_CURRENCY,
        "rules": {"competitive_threshold_usd": C.COMPETITIVE_THRESHOLD_USD,
                  "approval_tiers_usd": [[b if b != float("inf") else None, t] for b, t in C.APPROVAL_TIERS],
                  "tier_levels": C.TIER_LEVELS, "min_competitive_quotes": C.MIN_COMPETITIVE_QUOTES,
                  "budget_exception_cap": C.BUDGET_EXCEPTION_CAP,
                  "award_delivery_premium_max": C.AWARD_DELIVERY_PREMIUM_MAX,
                  "award_risk_premium_max": C.AWARD_RISK_PREMIUM_MAX},
        "params": asdict(cfg.params),
        "targets": {"requesters": scale.requesters, "suppliers": scale.suppliers, "purchase_request": scale.requests,
                    "rfq": scale.rfqs, "supplier_quote": scale.quotes, "purchase_order": scale.pos},
        "row_counts": counts,
        "ground_truth_by_issue_type": dict(sorted(by_type.items())),
        "provenance": {
            "source": "Fully synthetic. Generated by this repository's code from a fixed seed; no external datasets.",
            "external_data": [],
            "personal_data": "None. Person and company names are random combinations of generic words; "
                             "e-mail addresses use the reserved example.com domain.",
            "fx_rates": "Synthetic monthly random walk from illustrative starting values; not market data.",
            "license": "MIT (see LICENSE)",
        },
        "files": [{"path": p, "rows": n, "sha256": sha256(out_dir / p)} for p, n in files],
    }
