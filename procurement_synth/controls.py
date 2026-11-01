"""Rule-based control checks that surface exceptions from the published tables only.

`detect` never reads ground truth.  `reconcile` then compares its findings with the labels:
on a correct dataset every finding is labelled (no unexplained violations) and every label is
found, and on the clean baseline it finds nothing at all.
"""
from __future__ import annotations

from .checks_domain import Lookups, group, idx
from .config import DUPLICATE_WINDOW_DAYS, SPLIT_WINDOW_DAYS

TIER2_USD = 5_000
ALLOWED = {
    "PURCHASE_REQUEST": {(None, "SUBMITTED"), ("SUBMITTED", "PENDING_APPROVAL"), ("SUBMITTED", "SOURCING"),
                         ("SUBMITTED", "CANCELLED"), ("SOURCING", "PENDING_APPROVAL"), ("SOURCING", "CANCELLED"),
                         ("PENDING_APPROVAL", "APPROVED"), ("PENDING_APPROVAL", "REJECTED"),
                         ("PENDING_APPROVAL", "CANCELLED"), ("APPROVED", "ORDERED"), ("APPROVED", "CANCELLED"),
                         ("ORDERED", "PARTIALLY_RECEIVED"), ("ORDERED", "RECEIVED"),
                         ("PARTIALLY_RECEIVED", "RECEIVED"), ("PARTIALLY_RECEIVED", "CLOSED_SHORT")},
    "RFQ": {(None, "OPEN"), ("OPEN", "UNDER_EVALUATION"), ("OPEN", "CANCELLED"), ("UNDER_EVALUATION", "CANCELLED"),
            ("UNDER_EVALUATION", "AWARD_RECOMMENDED"), ("AWARD_RECOMMENDED", "AWARDED"),
            ("AWARD_RECOMMENDED", "AWARD_REJECTED"), ("AWARD_RECOMMENDED", "CANCELLED"), ("AWARDED", "CANCELLED")},
    "SUPPLIER_QUOTE": {(None, "RECEIVED"), ("RECEIVED", "SELECTED"), ("RECEIVED", "NOT_SELECTED"),
                       ("RECEIVED", "DISQUALIFIED"), ("RECEIVED", "CANCELLED"), ("SELECTED", "AWARDED"),
                       ("SELECTED", "AWARD_REJECTED"), ("SELECTED", "CANCELLED"), ("AWARDED", "CANCELLED")},
    "PURCHASE_ORDER": {(None, "ISSUED"), ("ISSUED", "PARTIALLY_RECEIVED"), ("ISSUED", "RECEIVED"),
                       ("PARTIALLY_RECEIVED", "RECEIVED"), ("PARTIALLY_RECEIVED", "CLOSED_SHORT")},
}


def detect(T) -> list[dict]:
    L = Lookups(T)
    out = []

    def hit(issue, entity_type, entity_id, related, detail):
        out.append({"issue_type": issue, "entity_type": entity_type, "entity_id": entity_id,
                    "related_ids": "|".join(related), "detail": detail})

    by_pr = group(T["approval"], "pr_id")
    po_prs = {}
    for l in T["po_line"]:
        po_prs.setdefault(l["po_id"], set()).add(l["pr_id"])
    for po in T["purchase_order"]:
        for pr_id in sorted(po_prs[po["po_id"]]):
            aps = by_pr.get(pr_id, [])
            late = [a["approval_id"] for a in aps if a["decision"] != "APPROVED" or a["decided_at"] > po["issued_at"]]
            if late or not aps:
                hit("PO_WITHOUT_APPROVAL", "PURCHASE_ORDER", po["po_id"], [pr_id] + late,
                    f"issued {po['issued_at']} before step(s) {', '.join(late) or 'none routed'} were approved")
        if L.status_on(po["supplier_id"], po["issued_at"].date()) != "ACTIVE":
            hit("INACTIVE_SUPPLIER", "PURCHASE_ORDER", po["po_id"], [po["supplier_id"]],
                f"supplier status {L.status_on(po['supplier_id'], po['issued_at'].date())} on the PO date")
    quotes, evals = idx(T["supplier_quote"], "quote_id"), idx(T["quote_evaluation"], "quote_id")
    rfqs = idx(T["rfq"], "rfq_id")
    for a in T["rfq_award"]:
        q, e = quotes[a["quote_id"]], evals[a["quote_id"]]
        if q["valid_until"] < a["recommended_at"].date():
            hit("QUOTE_EXPIRED_AT_AWARD", "RFQ", a["rfq_id"], [a["quote_id"]],
                f"valid until {q['valid_until']}, awarded {a['recommended_at']:%Y-%m-%d}")
        if rfqs[a["rfq_id"]]["sourcing_type"] == "COMPETITIVE" and e["is_eligible"] and e["landed_cost_rank"] > 1 \
                and not a["award_rationale"]:
            hit("NON_LOWEST_AWARD_NO_RATIONALE", "RFQ", a["rfq_id"], [a["quote_id"]],
                f"awarded rank {e['landed_cost_rank']} without rationale")
    for po in T["purchase_order"]:
        if po["source_type"] == "RFQ_AWARD" and po["currency_code"] != quotes[po["quote_id"]]["currency_code"]:
            hit("QUOTE_CURRENCY_MISMATCH", "PURCHASE_ORDER", po["po_id"], [po["quote_id"]],
                f"PO in {po['currency_code']}, quote in {quotes[po['quote_id']]['currency_code']}")
    for p in T["purchase_request"]:
        if p["budget_check_result"] == "OVER_BUDGET" and not any(
                a["approval_type"] == "BUDGET_EXCEPTION" for a in by_pr.get(p["pr_id"], [])):
            hit("BUDGET_OVERRUN", "PURCHASE_REQUEST", p["pr_id"], [p["budget_id"]],
                f"over budget at {p['budget_checked_at']} but no budget exception routed")
    _duplicates_and_splits(T, hit)
    return out


def _duplicates_and_splits(T, hit) -> None:
    lines = group(T["request_line"], "pr_id")
    sig = {p: tuple(sorted((l["item_id"], l["quantity"]) for l in ls)) for p, ls in lines.items()}
    items = {p: {l["item_id"] for l in ls} for p, ls in lines.items()}
    by_key = group(T["purchase_request"], "requester_id")
    for rid, prs in by_key.items():
        prs = sorted(prs, key=lambda p: p["submitted_at"])
        for i, p in enumerate(prs):
            for prev in prs[:i]:
                if prev["category_code"] == p["category_code"] and sig[prev["pr_id"]] == sig[p["pr_id"]] \
                        and (p["submitted_at"] - prev["submitted_at"]).days <= DUPLICATE_WINDOW_DAYS:
                    hit("DUPLICATE_REQUEST", "PURCHASE_REQUEST", p["pr_id"], [prev["pr_id"]],
                        f"same lines as {prev['pr_id']} submitted {(p['submitted_at'] - prev['submitted_at']).days}d earlier")
                    break
        used = set()
        for i, p in enumerate(prs):
            if p["pr_id"] in used or p["estimated_total_usd"] >= TIER2_USD:
                continue
            grp = [p] + [q for q in prs[i + 1:] if q["category_code"] == p["category_code"]
                         and q["estimated_total_usd"] < TIER2_USD and items[q["pr_id"]] & items[p["pr_id"]]
                         and sig[q["pr_id"]] != sig[p["pr_id"]]
                         and (q["submitted_at"] - p["submitted_at"]).days <= SPLIT_WINDOW_DAYS]
            if len(grp) > 1 and sum(g["estimated_total_usd"] for g in grp) >= TIER2_USD:
                used.update(g["pr_id"] for g in grp)
                hit("SPLIT_PURCHASE", "PURCHASE_REQUEST", p["pr_id"], [g["pr_id"] for g in grp[1:]],
                    f"{len(grp)} requests totalling {sum(g['estimated_total_usd'] for g in grp):,.2f} USD, each below 5,000")


def illegal_transitions(T) -> list[dict]:
    return [e for e in T["status_event"] if (e["from_status"], e["to_status"]) not in ALLOWED[e["entity_type"]]]


def reconcile(rep, T, gt) -> list[dict]:
    found = detect(T)
    types = sorted({g["issue_type"] for g in gt} | {f["issue_type"] for f in found})
    for t in types:
        labelled = {g["entity_id"] for g in gt if g["issue_type"] == t}
        hits = {f["entity_id"] for f in found if f["issue_type"] == t}
        fp, fn = sorted(hits - labelled), sorted(labelled - hits)
        rep.check("control", f"{t}: {len(hits)} detected / {len(labelled)} labelled", len(hits | labelled),
                  [f"unexplained {x}" for x in fp] + [f"undetected {x}" for x in fn],
                  note="every violation is labelled and every label is detected")
    bad = illegal_transitions(T)
    early = {pid for g in gt if g["issue_type"] == "PO_WITHOUT_APPROVAL" for pid in g["related_ids"].split("|") if pid.startswith("PR-")}
    unexplained = [e["event_id"] for e in bad if not (e["entity_type"] == "PURCHASE_REQUEST" and e["entity_id"] in early
                                                    and (e["from_status"], e["to_status"]) == ("PENDING_APPROVAL", "ORDERED"))]
    rep.check("control", f"lifecycle whitelist: {len(bad)} illegal transitions, all explained by PO_WITHOUT_APPROVAL",
              len(T["status_event"]), unexplained)
    return found
