"""Process KPIs and anomaly-detection scores computed from the published tables."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from .checks_domain import group, idx


def _pct(n, d) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def _hours(a, b) -> float:
    return (b - a).total_seconds() / 3600


def _q(values, q) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return round(values[min(len(values) - 1, int(q * len(values)))], 1)


def compute(T, gt, findings) -> dict:
    prs, pos, rfqs = T["purchase_request"], T["purchase_order"], T["rfq"]
    status = {}
    for p in prs:
        status[p["status"]] = status.get(p["status"], 0) + 1
    ordered = sum(v for k, v in status.items() if k in ("ORDERED", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED_SHORT"))
    by_pr = group(T["approval"], "pr_id")
    cycle = {}
    for p in prs:
        aps = by_pr.get(p["pr_id"], [])
        if aps and all(a["decision"] == "APPROVED" for a in aps):
            start = min(a["requested_at"] for a in aps)
            cycle.setdefault(p["approval_tier"], []).append(_hours(start, max(a["decided_at"] for a in aps)))
    reasons = {}
    for a in T["approval"]:
        if a["decision"] == "REJECTED":
            reasons[a["decision_reason"]] = reasons.get(a["decision_reason"], 0) + 1
    comp = [q for q in rfqs if q["sourcing_type"] == "COMPETITIVE"]
    awards = T["rfq_award"]
    evals = idx(T["quote_evaluation"], "quote_id")
    pr_by_id = idx(prs, "pr_id")
    rfq_by_id = idx(rfqs, "rfq_id")
    approved_awards = [a for a in awards if a["status"] == "APPROVED"]
    est = sum(pr_by_id[rfq_by_id[a["rfq_id"]]["pr_id"]]["estimated_total_usd"] for a in approved_awards)
    landed = sum(a["awarded_landed_cost_usd"] for a in approved_awards)
    basis = {}
    for a in awards:
        basis[a["award_basis"] or "NONE_RECORDED"] = basis.get(a["award_basis"] or "NONE_RECORDED", 0) + 1
    dels = group(T["delivery"], "po_id")
    first_on_time = [min(d, key=lambda x: x["delivery_seq"])["is_on_time"] for d in dels.values()]
    closed = [p for p in pos if p["status"] in ("RECEIVED", "CLOSED_SHORT")]
    otif = [p for p in closed if p["status"] == "RECEIVED" and all(d["is_on_time"] for d in dels[p["po_id"]])]
    partial = [p for p in pos if len(dels.get(p["po_id"], [])) > 1 or p["status"] == "CLOSED_SHORT"]
    late = [d["days_late"] for d in T["delivery"] if d["days_late"] > 0]
    units = sum(l["qty_delivered"] for l in T["delivery_line"])
    rejected = sum(l["qty_rejected"] for l in T["delivery_line"])
    pol = group(T["po_line"], "po_id")
    consolidated = [p for p in pos if len({l["pr_id"] for l in pol[p["po_id"]]}) > 1]
    over = [p for p in prs if p["budget_check_result"] == "OVER_BUDGET"]
    exc_dec = {}
    for a in T["approval"]:
        if a["approval_type"] == "BUDGET_EXCEPTION":
            exc_dec[a["decision"]] = exc_dec.get(a["decision"], 0) + 1
    exc = {}
    for e in T["exception_register"]:
        exc[e["exception_type"]] = exc.get(e["exception_type"], 0) + 1
    detection = {}
    for t in sorted({g["issue_type"] for g in gt} | {f["issue_type"] for f in findings}):
        lab = {g["entity_id"] for g in gt if g["issue_type"] == t}
        hit = {f["entity_id"] for f in findings if f["issue_type"] == t}
        tp = len(lab & hit)
        prec, rec = (tp / len(hit) if hit else 1.0), (tp / len(lab) if lab else 1.0)
        detection[t] = {"labelled": len(lab), "detected": len(hit), "true_positive": tp, "precision": round(prec, 3),
                        "recall": round(rec, 3), "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0}
    util = sorted((b["utilization_pct"] for b in T["budget_balance"]
                   if idx(T["budget"], "budget_id")[b["budget_id"]]["budget_type"] != "CONTINGENCY"))
    return {
        "volumes": {k: len(v) for k, v in T.items()},
        "requests": {"status": dict(sorted(status.items())), "pr_to_po_conversion_pct": _pct(ordered, len(prs)),
                     "rejection_rate_pct": _pct(status.get("REJECTED", 0), len(prs)),
                     "cancellation_rate_pct": _pct(status.get("CANCELLED", 0), len(prs)),
                     "rejection_reasons": dict(sorted(reasons.items()))},
        "approvals": {"steps": len(T["approval"]),
                      "cycle_hours_by_tier": {str(k): {"n": len(v), "median": _q(v, 0.5), "p90": _q(v, 0.9)}
                                              for k, v in sorted(cycle.items())}},
        "sourcing": {"rfqs": len(rfqs), "single_source_pct": _pct(len(rfqs) - len(comp), len(rfqs)),
                     "avg_quotes_competitive": round(statistics.mean(q["quotes_received"] for q in comp), 2) if comp else 0,
                     "competitive_with_3plus_quotes_pct": _pct(sum(1 for q in comp if q["quotes_received"] >= 3), len(comp)),
                     "award_basis": dict(sorted(basis.items())),
                     "awarded_lowest_landed_cost_pct": _pct(sum(1 for a in awards if evals[a["quote_id"]]["landed_cost_rank"] == 1), len(awards)),
                     "savings_vs_estimate_pct": _pct(est - landed, est),
                     "quotes_expired_before_evaluation_pct": _pct(sum(1 for e in T["quote_evaluation"] if not e["is_valid_at_evaluation"]),
                                                                  len(T["quote_evaluation"])),
                     "non_usd_quotes_pct": _pct(sum(1 for q in T["supplier_quote"] if q["currency_code"] != "USD"), len(T["supplier_quote"]))},
        "purchase_orders": {"count": len(pos), "rfq_award": sum(1 for p in pos if p["source_type"] == "RFQ_AWARD"),
                            "direct_contract": sum(1 for p in pos if p["source_type"] == "DIRECT_CONTRACT"),
                            "consolidated_pct": _pct(len(consolidated), len(pos)),
                            "total_committed_usd": round(sum(p["total_usd"] for p in pos), 2),
                            "median_po_usd": _q([p["total_usd"] for p in pos], 0.5)},
        "delivery": {"deliveries": len(T["delivery"]), "first_delivery_on_time_pct": _pct(sum(first_on_time), len(first_on_time)),
                     "otif_pct_of_closed_pos": _pct(len(otif), len(closed)), "partial_or_short_po_pct": _pct(len(partial), len(pos)),
                     "short_closed_pos": sum(1 for p in pos if p["status"] == "CLOSED_SHORT"),
                     "median_days_late_when_late": _q(late, 0.5), "quality_rejection_units_pct": _pct(rejected, units)},
        "budget": {"over_budget_requests": len(over), "budget_exception_decisions": dict(sorted(exc_dec.items())),
                   "transfers_usd": round(sum(t["allocated_delta_usd"] for t in T["budget_transaction"] if t["txn_type"] == "TRANSFER_IN"), 2),
                   "utilization_median": _q(util, 0.5), "budgets_over_90pct": sum(1 for u in util if u > 0.9)},
        "exceptions": dict(sorted(exc.items())),
        "anomaly_detection": detection,
    }


def write(T, gt, findings, manifest, out_dir: Path) -> dict:
    m = compute(T, gt, findings)
    (out_dir / "metrics.json").write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8", newline="")
    r, s, d, b = m["requests"], m["sourcing"], m["delivery"], m["budget"]
    lines = [f"# Process metrics - {manifest['scale']['name']} (seed {manifest['seed']})", "",
             "## Volumes vs brief", "", "| Entity | Target | Actual |", "|---|---:|---:|"]
    tmap = {"requesters": "requester", "suppliers": "supplier"}
    for k, v in manifest["targets"].items():
        lines.append(f"| {k} | {v} | {m['volumes'][tmap.get(k, k)]} |")
    lines += ["", "## Key indicators", "", "| Area | Indicator | Value |", "|---|---|---:|",
              f"| Requests | PR -> PO conversion | {r['pr_to_po_conversion_pct']}% |",
              f"| Requests | Rejected / cancelled | {r['rejection_rate_pct']}% / {r['cancellation_rate_pct']}% |",
              f"| Sourcing | Competitive RFQs with >= 3 quotes | {s['competitive_with_3plus_quotes_pct']}% |",
              f"| Sourcing | Avg quotes per competitive RFQ | {s['avg_quotes_competitive']} |",
              f"| Sourcing | Single-source share of RFQs | {s['single_source_pct']}% |",
              f"| Sourcing | Awards to lowest eligible landed cost | {s['awarded_lowest_landed_cost_pct']}% |",
              f"| Sourcing | Savings vs requester estimate (approved awards) | {s['savings_vs_estimate_pct']}% |",
              f"| Sourcing | Quotes expired at evaluation | {s['quotes_expired_before_evaluation_pct']}% |",
              f"| Orders | POs (RFQ award / direct) | {m['purchase_orders']['rfq_award']} / {m['purchase_orders']['direct_contract']} |",
              f"| Orders | Consolidated direct POs | {m['purchase_orders']['consolidated_pct']}% |",
              f"| Delivery | First delivery on time | {d['first_delivery_on_time_pct']}% |",
              f"| Delivery | OTIF (closed POs) | {d['otif_pct_of_closed_pos']}% |",
              f"| Delivery | POs with partial delivery or short close | {d['partial_or_short_po_pct']}% |",
              f"| Delivery | Units rejected at inspection | {d['quality_rejection_units_pct']}% |",
              f"| Budget | Over-budget requests | {b['over_budget_requests']} |",
              f"| Budget | Budget exception decisions | {b['budget_exception_decisions']} |",
              "", "## Approval cycle time (hours, fully approved chains)", "", "| Tier | n | Median | P90 |", "|---|---:|---:|---:|"]
    lines += [f"| {k} | {v['n']} | {v['median']} | {v['p90']} |" for k, v in m["approvals"]["cycle_hours_by_tier"].items()]
    lines += ["", "## Documented business exceptions", "", "| Type | Count |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in m["exceptions"].items()]
    lines += ["", "## Control checks vs ground truth", "",
              "Rule-based checks in `procurement_synth/controls.py` read only the published tables.", "",
              "| Issue type | Labelled | Detected | Precision | Recall | F1 |", "|---|---:|---:|---:|---:|---:|"]
    lines += [f"| {k} | {v['labelled']} | {v['detected']} | {v['precision']} | {v['recall']} | {v['f1']} |"
              for k, v in m["anomaly_detection"].items()]
    (out_dir / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    return m
