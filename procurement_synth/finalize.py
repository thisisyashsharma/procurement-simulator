"""Assemble exported tables: strip latent fields, derive statuses, balances and the exception register."""
from __future__ import annotations

from .schema import TABLES, columns
from .util import money, seq_id


def _clean(rows, table):
    cols = columns(table)
    return [{c: row.get(c) for c in cols} for row in rows]


def finalize(w, prs, rfqs, eng, ev) -> dict[str, list[dict]]:
    last = ev.last_status()
    for pr in prs:
        pr["status"], pr["status_updated_at"] = last[("PURCHASE_REQUEST", pr["pr_id"])]
    quotes, qlines, evals, awards, invites = [], [], [], [], []
    for q in rfqs:
        q["status"] = last[("RFQ", q["rfq_id"])][0]
        q["quotes_received"] = len(q["_quotes"])
        invites += q["_invites"]
        evals += q["_evals"]
        if q["_award"]:
            awards.append(q["_award"])
        for qt in q["_quotes"]:
            qt["status"] = last[("SUPPLIER_QUOTE", qt["quote_id"])][0]
            quotes.append(qt)
            qlines += qt["_lines"]
    for po in eng.pos:
        po["status"] = last[("PURCHASE_ORDER", po["po_id"])][0]
    _early_po_outcomes(eng)
    events = sorted(ev.rows, key=lambda e: (e["event_ts"], e["_seq"]))
    for n, e in enumerate(events, 1):
        e["event_id"] = seq_id("EVT", n)
    tables = {
        "department": w.departments, "requester": w.requesters, "item_category": w.categories,
        "supplier": w.suppliers, "item": w.items, "supplier_category": w.supplier_categories,
        "supplier_status_history": w.supplier_status, "supplier_risk_flag": w.risk_flags, "fx_rate": w.fx_rates,
        "budget": w.budgets, "purchase_request": prs, "request_line": [ln for pr in prs for ln in pr["_lines"]],
        "rfq": rfqs, "rfq_supplier": invites, "supplier_quote": quotes, "quote_line": qlines,
        "quote_evaluation": evals, "rfq_award": awards, "approval": eng.approvals, "purchase_order": eng.pos,
        "po_line": eng.po_lines, "delivery": eng.deliveries, "delivery_line": eng.delivery_lines,
        "budget_transaction": eng.ledger.rows, "budget_balance": _balances(w, eng.ledger.rows),
        "status_event": events,
    }
    tables["exception_register"] = _exceptions(tables, rfqs)
    out = {}
    for t in TABLES:
        rows = _clean(tables[t.name], t.name)
        out[t.name] = sorted(rows, key=lambda r: tuple(str(r[k]) for k in t.pk))
    return out


def _early_po_outcomes(eng) -> None:
    for st in eng.st.values():
        row = st.get("gt_row")
        if not row:
            continue
        decisions = [a["decision"] for a in eng.approvals if a["_st"] is st]
        row["sub_type"] = ("APPROVAL_REJECTED_AFTER_PO" if "REJECTED" in decisions
                           else "APPROVAL_STILL_PENDING" if "PENDING" in decisions else "APPROVED_AFTER_PO")
        row["evidence"]["approval_outcome_at_snapshot"] = row["sub_type"]


def _balances(w, ledger_rows) -> list[dict]:
    acc = {b["budget_id"]: [0.0, 0.0, 0.0] for b in w.budgets}
    for t in ledger_rows:
        a = acc[t["budget_id"]]
        a[0] += t["allocated_delta_usd"]
        a[1] += t["reserved_delta_usd"]
        a[2] += t["committed_delta_usd"]
    out = []
    for b in w.budgets:
        tr, res, com = (money(x) for x in acc[b["budget_id"]])
        current = money(b["allocated_amount_usd"] + tr)
        out.append({"budget_id": b["budget_id"], "allocated_original_usd": b["allocated_amount_usd"],
                    "transfers_net_usd": tr, "allocated_current_usd": current, "reserved_usd": res,
                    "committed_usd": com, "available_usd": money(current - res - com),
                    "utilization_pct": round((res + com) / current, 4) if current else 0.0})
    return out


def _exceptions(t: dict, rfqs: list[dict]) -> list[dict]:
    rows = []

    def add(etype, entity_type, entity_id, pr_id, raised, code, text, approval=None, resolution="RECORDED",
            resolved=None):
        rows.append({"exception_type": etype, "entity_type": entity_type, "entity_id": entity_id, "pr_id": pr_id,
                     "raised_at": raised, "reason_code": code, "reason_text": text,
                     "approval_id": approval["approval_id"] if approval else None,
                     "resolution": approval["decision"] if approval else resolution,
                     "resolved_at": approval["decided_at"] if approval else resolved})

    prs = {p["pr_id"]: p for p in t["purchase_request"]}
    by_pr_type = {}
    for a in t["approval"]:
        by_pr_type[(a["pr_id"], a["approval_type"])] = a
        if a["approval_type"] == "BUDGET_EXCEPTION":
            p = prs[a["pr_id"]]
            add("BUDGET_EXCEPTION", "PURCHASE_REQUEST", a["pr_id"], a["pr_id"], a["requested_at"], "OVER_BUDGET",
                f"{p['approval_basis_usd']:,.2f} USD requested vs {p['budget_available_usd']:,.2f} USD available "
                f"in {p['budget_id']}; overrun {a['basis_amount_usd']:,.2f} USD.", a)
        elif a["approval_type"] == "COMPETITION_WAIVER":
            q = next(r for r in rfqs if r["rfq_id"] == a["rfq_id"])
            add("COMPETITION_WAIVER", "RFQ", a["rfq_id"], a["pr_id"], a["requested_at"], "INSUFFICIENT_BIDS",
                f"{q['quotes_received']} quote(s) received; {q['min_quotes_required']} required.", a)
    for q in rfqs:
        if q["sourcing_type"] == "SINGLE_SOURCE":
            appr = by_pr_type.get((q["pr_id"], "SINGLE_SOURCE"))
            add("SINGLE_SOURCE", "RFQ", q["rfq_id"], q["pr_id"], q["issued_at"], q["single_source_reason"],
                "Only one qualified source: " + ("OEM-certified item" if q["single_source_reason"] == "SOLE_SOURCE_OEM"
                                                 else "critical need inside the 10-day emergency window") + ".",
                appr, resolution="PENDING")
        award = q["_award"]
        if q["cancel_reason"] == "AWARDED_SUPPLIER_INACTIVE":
            add("SUPPLIER_DISQUALIFIED", "RFQ", q["rfq_id"], q["pr_id"], q["_withdrawn_at"], "AWARDED_SUPPLIER_INACTIVE",
                f"Awarded supplier {award['supplier_id']} became inactive before the PO; award withdrawn.",
                resolution="WITHDRAWN", resolved=q["_withdrawn_at"])
        if award and award["award_basis"] in ("DELIVERY_REQUIREMENT", "RISK_MITIGATION"):
            add("NON_LOWEST_AWARD", "RFQ", q["rfq_id"], q["pr_id"], award["recommended_at"], award["award_basis"],
                award["award_rationale"], resolved=award["recommended_at"])
        for e in q["_evals"]:
            if e["is_eligible"] or (award and award["quote_id"] == e["quote_id"]):
                continue
            etype = "QUOTE_EXPIRED" if e["disqualification_reason"] == "EXPIRED" else "SUPPLIER_DISQUALIFIED"
            text = (f"Valid until {e['_quote']['valid_until']}; evaluated {e['evaluated_at']:%Y-%m-%d}."
                    if etype == "QUOTE_EXPIRED" else
                    f"Supplier {e['_quote']['supplier_id']} was {e['supplier_status_at_evaluation']} / risk "
                    f"{e['supplier_risk_at_evaluation']} at evaluation.")
            add(etype, "SUPPLIER_QUOTE", e["quote_id"], q["pr_id"], e["evaluated_at"], e["disqualification_reason"],
                text, resolution="EXCLUDED", resolved=e["evaluated_at"])
    po_pr = {}
    for ln in t["po_line"]:
        po_pr.setdefault(ln["po_id"], ln["pr_id"])
    pos = {p["po_id"]: p for p in t["purchase_order"]}
    for d in t["delivery"]:
        if d["days_late"] > 0:
            add("LATE_DELIVERY", "DELIVERY", d["delivery_id"], po_pr[d["po_id"]], d["delivered_at"], "LATE",
                f"Received {d['days_late']} day(s) after the promised date {pos[d['po_id']]['promised_date']}.",
                resolved=d["delivered_at"])
        if not d["completes_po"]:
            add("PARTIAL_DELIVERY", "DELIVERY", d["delivery_id"], po_pr[d["po_id"]], d["delivered_at"],
                "BALANCE_OUTSTANDING", "Partial receipt; balance remains open on the PO.", resolved=d["delivered_at"])
    deliveries = {d["delivery_id"]: d for d in t["delivery"]}
    for dl in t["delivery_line"]:
        if dl["qty_rejected"]:
            d = deliveries[dl["delivery_id"]]
            add("QUALITY_REJECTION", "DELIVERY", dl["delivery_id"], po_pr[d["po_id"]], d["delivered_at"],
                dl["rejection_reason"], f"{dl['qty_rejected']} of {dl['qty_delivered']} unit(s) rejected on "
                                        f"{dl['po_line_id']}.", resolved=d["delivered_at"])
    for p in t["purchase_order"]:
        if p["status"] == "CLOSED_SHORT":
            open_units = sum(ln["quantity"] - ln["qty_received"] for ln in p["_lines"])
            add("SHORT_CLOSE", "PURCHASE_ORDER", p["po_id"], po_pr[p["po_id"]], p["closed_at"], "SUPPLIER_SHORT_SHIP",
                f"{open_units} unit(s) not supplied; PO closed short and the open commitment released.",
                resolved=p["closed_at"])
    rows.sort(key=lambda r: (r["raised_at"], r["exception_type"], r["entity_id"]))
    for n, r in enumerate(rows, 1):
        r["exception_id"] = seq_id("EXC", n)
    return rows
