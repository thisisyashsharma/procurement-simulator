"""Generate docs/data_dictionary.md from schema.py so the dictionary can never drift from the data."""
from __future__ import annotations

from pathlib import Path

from .schema import GROUND_TRUTH_COLUMNS, TABLE_BY_NAME, TABLES

KIND_NOTE = {"master": "Master data", "reference": "Reference data", "bridge": "Bridge (N:M)",
             "transaction": "Transaction", "event": "Event / history (append-only)", "derived": "Derived"}


def relationships() -> list[tuple]:
    rels = []
    for t in TABLES:
        for c in t.cols:
            if not c.fk:
                continue
            parent, pcol = c.fk.split(".")
            one_to_one = c.unique and not (len(t.pk) > 1)
            card = "1 : 0..1" if one_to_one else "1 : N"
            opt = "optional" if not c.required else "mandatory"
            rels.append((parent, t.name, f"{t.name}.{c.name} -> {parent}.{pcol}", card, opt))
    return rels


def write_data_dictionary(path: Path) -> None:
    out = ["# Data dictionary", "",
           "Generated from `procurement_synth/schema.py` (`python -m procurement_synth docs`). "
           "Types are logical; the SQL seed uses the same names. Money columns are rounded half-up to cents; "
           "`derived` columns are recomputed from source records and re-checked by the validator.", "",
           "## Tables", "", "| Table | Kind | Primary key | Description |", "|---|---|---|---|"]
    out += [f"| [{t.name}](#{t.name}) | {KIND_NOTE[t.kind]} | {', '.join(t.pk)} | {t.desc} |" for t in TABLES]
    out += ["", "## Relationships and cardinality", "",
            "Every foreign key below is enforced in `sql/schema.sql` and validated on export. "
            "`budget_transaction.source_id`, `status_event.entity_id` and `exception_register.entity_id` are "
            "polymorphic references (the target table is given by the type column); the validator resolves them.", "",
            "| Parent | Child | Key | Cardinality | Child side |", "|---|---|---|---|---|"]
    out += [f"| {p} | {c} | `{k}` | {card} | {opt} |" for p, c, k, card, opt in relationships()]
    out += ["", "Many-to-many relationships are resolved through bridge tables: supplier <-> item_category "
            "(`supplier_category`), RFQ <-> supplier (`rfq_supplier`) and purchase request <-> purchase order "
            "(`po_line`, one row per ordered request line; direct-buy POs can consolidate several requests).", ""]
    for t in TABLES:
        out += [f"## {t.name}", "", f"{t.desc}  ", f"*Kind:* {KIND_NOTE[t.kind]}. *Primary key:* `{', '.join(t.pk)}`."
                + (f" *Natural keys:* {', '.join('(' + ', '.join(u) + ')' for u in t.unique)}." if t.unique else ""), "",
                "| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |",
                "|---|---|:-:|---|---|:-:|---|---|"]
        for c in t.cols:
            allowed = ", ".join(map(str, c.enum)) if c.enum else (f"`{c.pattern}`" if c.pattern else "")
            rule = "; ".join(x for x in (f"FK {c.fk}" if c.fk else "", c.rule or "", "derived" if c.derived else "") if x)
            out.append(f"| {c.name} | {c.type} | {'Y' if c.required else ''} | {allowed} | {c.unit or ''} | "
                       f"{'Y' if c.unique or t.pk == (c.name,) else ''} | {rule} | {c.desc} |")
        out.append("")
    out += ["## ground_truth (separate folder, never joined into inputs)", "",
            "| Column | Description |", "|---|---|"]
    out += [f"| {c} | {d} |" for c, d in GROUND_TRUTH_COLUMNS]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="")


def table(name: str):
    return TABLE_BY_NAME[name]
