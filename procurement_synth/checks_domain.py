"""Domain integrity checks: date ordering, arithmetic reconciliation, budget ledger, lifecycle
continuity and the brief's acceptance criteria.  All of these must pass on every dataset."""
from __future__ import annotations

from datetime import timedelta

from .config import ROLE_RANK, TIER_LEVELS, tier_for
from .util import add_business_days, money

TOL = 0.011
LEVEL_RANK = {"MANAGER": 2, "DIRECTOR": 3, "VP": 4, "CFO": 5}
SEV = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


def idx(rows, key):
    return {r[key]: r for r in rows}


def group(rows, key):
    out = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


def eq(a, b) -> bool:
    return abs((a or 0.0) - (b or 0.0)) <= TOL


class Lookups:
    def __init__(self, T):
        self.fx = {(f["currency_code"], f["rate_month"]): f["usd_per_unit"] for f in T["fx_rate"]}
        self.status = group(T["supplier_status_history"], "supplier_id")
        self.flags = group(T["supplier_risk_flag"], "supplier_id")
        self.sup, self.item, self.cat = idx(T["supplier"], "supplier_id"), idx(T["item"], "item_id"), idx(T["item_category"], "category_code")
        self.req = idx(T["requester"], "requester_id")
        self.disc = {(s["supplier_id"], s["category_code"]): s["contract_discount_pct"] or 0.0 for s in T["supplier_category"]}

    def rate(self, cur, d):
        return self.fx[(cur, f"{d.year:04d}-{d.month:02d}")]

    def status_on(self, sid, d):
        s = "INACTIVE"
        for h in sorted(self.status.get(sid, ()), key=lambda h: h["effective_from"]):
            if h["effective_from"] <= d:
                s = h["status"]
        return s

    def risk_on(self, sid, d):
        lvl = "NONE"
        for f in self.flags.get(sid, ()):
            if f["raised_date"] <= d and (f["cleared_date"] is None or d < f["cleared_date"]) and SEV[f["severity"]] > SEV[lvl]:
                lvl = f["severity"]
        return lvl


def run(rep, T) -> None:
    L = Lookups(T)
    dates(rep, T, L)
    arithmetic(rep, T, L)
    purchase_orders(rep, T, L)
    budget(rep, T)
    lifecycle(rep, T)
    acceptance(rep, T, L)


def dates(rep, T, L) -> None:
    pr, rfq = idx(T["purchase_request"], "pr_id"), idx(T["rfq"], "rfq_id")
    po = idx(T["purchase_order"], "po_id")
    rep.check("date_order", "requester termination_date >= hire_date", len(T["requester"]),
              [r["requester_id"] for r in T["requester"] if r["termination_date"] and r["termination_date"] < r["hire_date"]])
    rep.check("date_order", "requester employed on the request submission date", len(pr),
              [p["pr_id"] for p in pr.values() if not (L.req[p["requester_id"]]["hire_date"] <= p["submitted_at"].date()
               and (L.req[p["requester_id"]]["termination_date"] is None or p["submitted_at"].date() < L.req[p["requester_id"]]["termination_date"]))])
    rep.check("date_order", "need_by_date after submission", len(pr),
              [p["pr_id"] for p in pr.values() if p["need_by_date"] <= p["submitted_at"].date()])
    rep.check("date_order", "RFQ issued >= request submitted; due > issued; evaluated >= due", len(rfq),
              [q["rfq_id"] for q in rfq.values() if q["issued_at"] < pr[q["pr_id"]]["submitted_at"]
               or q["response_due_at"] <= q["issued_at"] or (q["evaluated_at"] and q["evaluated_at"] < q["response_due_at"])])
    rep.check("date_order", "quote submitted within the RFQ bid window; valid_until >= submission", len(T["supplier_quote"]),
              [q["quote_id"] for q in T["supplier_quote"] if not (rfq[q["rfq_id"]]["issued_at"] <= q["submitted_at"]
               <= rfq[q["rfq_id"]]["response_due_at"]) or q["valid_until"] < q["submitted_at"].date()])
    rep.check("date_order", "invitation response after invitation", len(T["rfq_supplier"]),
              [(i["rfq_id"], i["supplier_id"]) for i in T["rfq_supplier"] if i["responded_at"] and i["responded_at"] < i["invited_at"]])
    rep.check("date_order", "approval requested after submission (and after evaluation for awards); decided >= requested",
              len(T["approval"]), [a["approval_id"] for a in T["approval"] if a["requested_at"] < pr[a["pr_id"]]["submitted_at"]
               or (a["rfq_id"] and a["requested_at"] < rfq[a["rfq_id"]]["evaluated_at"])
               or (a["decided_at"] and a["decided_at"] < a["requested_at"])])
    pol = group(T["po_line"], "po_id")
    rep.check("date_order", "PO issued after every request it fulfils (and after RFQ evaluation)", len(po),
              [p["po_id"] for p in po.values() if any(p["issued_at"] < pr[l["pr_id"]]["submitted_at"] for l in pol[p["po_id"]])
               or (p["rfq_id"] and p["issued_at"] < rfq[p["rfq_id"]]["evaluated_at"])])
    rep.check("date_order", "delivery after PO issue", len(T["delivery"]),
              [d["delivery_id"] for d in T["delivery"] if d["delivered_at"] <= po[d["po_id"]]["issued_at"]])
    bad = []
    for sid, rows in L.status.items():
        rows = sorted(rows, key=lambda h: h["effective_from"])
        for a, b in zip(rows, rows[1:]):
            if a["effective_to"] != b["effective_from"]:
                bad.append(sid)
        if rows[-1]["effective_to"] is not None:
            bad.append(sid)
    rep.check("date_order", "supplier status history is contiguous (half-open intervals)", len(L.status), bad)
    rep.check("date_order", "risk flag cleared after raised", len(T["supplier_risk_flag"]),
              [f["risk_flag_id"] for f in T["supplier_risk_flag"] if f["cleared_date"] and f["cleared_date"] <= f["raised_date"]])


def arithmetic(rep, T, L) -> None:
    lines = group(T["request_line"], "pr_id")
    rep.check("arithmetic", "request_line total = quantity x estimated unit price", len(T["request_line"]),
              [l["pr_line_id"] for l in T["request_line"] if not eq(l["est_line_total_usd"], money(l["quantity"] * l["est_unit_price_usd"]))])
    rep.check("arithmetic", "request estimated_total = sum of its lines", len(T["purchase_request"]),
              [p["pr_id"] for p in T["purchase_request"] if not eq(p["estimated_total_usd"], sum(l["est_line_total_usd"] for l in lines[p["pr_id"]]))])
    ql = group(T["quote_line"], "quote_id")
    rep.check("arithmetic", "quote_line amount = quantity x unit price", len(T["quote_line"]),
              [l["quote_line_id"] for l in T["quote_line"] if not eq(l["line_amount"], money(l["quantity"] * l["unit_price"]))])
    rep.check("arithmetic", "quote goods = sum of lines; total = goods + freight", len(T["supplier_quote"]),
              [q["quote_id"] for q in T["supplier_quote"] if not eq(q["goods_amount"], sum(l["line_amount"] for l in ql[q["quote_id"]]))
               or not eq(q["total_amount"], q["goods_amount"] + q["freight_amount"])])
    quotes, rfqs, prs = idx(T["supplier_quote"], "quote_id"), idx(T["rfq"], "rfq_id"), idx(T["purchase_request"], "pr_id")
    bad = []
    for e in T["quote_evaluation"]:
        q = quotes[e["quote_id"]]
        fx = L.rate(q["currency_code"], q["submitted_at"])
        goods, freight = money(q["goods_amount"] * fx), money(q["freight_amount"] * fx)
        cat = L.cat[prs[rfqs[q["rfq_id"]]["pr_id"]]["category_code"]]
        duty = money(goods * cat["import_duty_rate"]) if L.sup[q["supplier_id"]]["country_code"] != "US" and q["incoterm"] != "DDP" else 0.0
        d = e["evaluated_at"].date()
        valid = q["valid_until"] >= d
        status, risk = L.status_on(q["supplier_id"], d), L.risk_on(q["supplier_id"], d)
        expected = add_business_days(d, 2) + timedelta(days=q["lead_time_days"])
        if not (eq(e["fx_rate_used"], fx) and eq(e["goods_usd"], goods) and eq(e["freight_usd"], freight)
                and eq(e["duty_usd"], duty) and eq(e["landed_cost_usd"], money(goods + freight + duty))
                and e["is_valid_at_evaluation"] == valid and e["supplier_status_at_evaluation"] == status
                and e["supplier_risk_at_evaluation"] == risk and e["expected_delivery_date"] == expected
                and e["meets_need_by"] == (expected <= prs[rfqs[q["rfq_id"]]["pr_id"]]["need_by_date"])
                and e["is_eligible"] == (valid and status == "ACTIVE" and risk != "HIGH")):
            bad.append(e["quote_id"])
    rep.check("arithmetic", "quote_evaluation recomputes (FX of quote month, duty rule, landed cost, eligibility)",
              len(T["quote_evaluation"]), bad)
    bad = []
    for rid, evs in group(T["quote_evaluation"], "rfq_id").items():
        elig = sorted((e for e in evs if e["is_eligible"]), key=lambda e: (e["landed_cost_usd"], e["quote_id"]))
        if [e["landed_cost_rank"] for e in elig] != list(range(1, len(elig) + 1)) or any(
                e["landed_cost_rank"] is not None for e in evs if not e["is_eligible"]):
            bad.append(rid)
    rep.check("arithmetic", "landed_cost_rank is the rank among eligible quotes", len(T["rfq"]), bad)


def purchase_orders(rep, T, L) -> None:
    pol, ql = group(T["po_line"], "po_id"), idx(T["quote_line"], "quote_line_id")
    ql_by_quote = group(T["quote_line"], "quote_id")
    quotes, awards = idx(T["supplier_quote"], "quote_id"), idx(T["rfq_award"], "rfq_id")
    rl = idx(T["request_line"], "pr_line_id")
    rep.check("arithmetic", "po_line amount = quantity x unit price; quantity and item = request line", len(T["po_line"]),
              [l["po_line_id"] for l in T["po_line"] if not eq(l["line_amount"], money(l["quantity"] * l["unit_price"]))
               or l["quantity"] != rl[l["pr_line_id"]]["quantity"] or l["item_id"] != rl[l["pr_line_id"]]["item_id"]
               or rl[l["pr_line_id"]]["pr_id"] != l["pr_id"]])
    bad_tot, bad_q, bad_d = [], [], []
    for p in T["purchase_order"]:
        lines = sorted(pol[p["po_id"]], key=lambda l: l["line_no"])
        fx = L.rate(p["currency_code"], p["issued_at"])
        goods = money(sum(l["line_amount"] for l in lines))
        cat = L.cat[L.item[lines[0]["item_id"]]["category_code"]]
        duty = money(money(goods * fx) * cat["import_duty_rate"]) if L.sup[p["supplier_id"]]["country_code"] != "US" and p["incoterm"] != "DDP" else 0.0
        if not (eq(p["goods_amount"], goods) and eq(p["total_amount"], goods + p["freight_amount"]) and eq(p["fx_rate_to_usd"], fx)
                and eq(p["est_duty_usd"], duty) and eq(p["total_usd"], money(money(p["total_amount"] * fx) + duty))):
            bad_tot.append(p["po_id"])
        if p["source_type"] == "RFQ_AWARD":
            q = quotes[p["quote_id"]]
            mapped = [ql.get(l["quote_line_id"]) for l in lines]
            if (awards[p["rfq_id"]]["quote_id"] != p["quote_id"] or q["supplier_id"] != p["supplier_id"]
                    or not eq(q["freight_amount"], p["freight_amount"]) or len(mapped) != len(ql_by_quote[q["quote_id"]])
                    or any(x is None or x["quote_id"] != q["quote_id"] or x["quantity"] != l["quantity"]
                           or not eq(x["unit_price"], l["unit_price"]) or x["pr_line_id"] != l["pr_line_id"]
                           for x, l in zip(mapped, lines))):
                bad_q.append(p["po_id"])
        else:
            for l in lines:
                it = L.item[l["item_id"]]
                if not eq(l["unit_price"], money(it["list_price_usd"] * (1 - L.disc.get((p["supplier_id"], it["category_code"]), 0.0)))):
                    bad_d.append(l["po_line_id"])
    n_rfq = sum(1 for p in T["purchase_order"] if p["source_type"] == "RFQ_AWARD")
    rep.check("arithmetic", "PO goods/total/FX/duty/total_usd recompute", len(T["purchase_order"]), bad_tot)
    rep.check("acceptance", "RFQ PO lines, prices, quantities and freight equal the awarded quote lines", n_rfq, bad_q)
    rep.check("acceptance", "direct PO prices = list price x (1 - supplier contract discount)",
              len(T["purchase_order"]) - n_rfq, bad_d)
    acc = {}
    for d in T["delivery_line"]:
        acc[d["po_line_id"]] = acc.get(d["po_line_id"], 0) + d["qty_accepted"]
    pos = idx(T["purchase_order"], "po_id")
    rep.check("arithmetic", "po_line qty_received = sum of accepted delivery quantities; status consistent", len(T["po_line"]),
              [l["po_line_id"] for l in T["po_line"] if l["qty_received"] != acc.get(l["po_line_id"], 0)
               or l["qty_received"] > l["quantity"] or l["line_status"] != (
                   "RECEIVED" if l["qty_received"] >= l["quantity"] else "CLOSED_SHORT" if pos[l["po_id"]]["status"] == "CLOSED_SHORT"
                   else "PARTIALLY_RECEIVED" if l["qty_received"] else "OPEN")])
    rep.check("arithmetic", "delivery_line accepted + rejected = delivered; reason iff rejected", len(T["delivery_line"]),
              [d["delivery_line_id"] for d in T["delivery_line"] if d["qty_accepted"] + d["qty_rejected"] != d["qty_delivered"]
               or d["qty_delivered"] <= 0 or bool(d["qty_rejected"]) != bool(d["rejection_reason"])])
    bad = []
    dl = group(T["delivery_line"], "delivery_id")
    for po_id, dels in group(T["delivery"], "po_id").items():
        p = pos[po_id]
        got = {}
        for d in sorted(dels, key=lambda d: d["delivery_seq"]):
            for x in dl[d["delivery_id"]]:
                got[x["po_line_id"]] = got.get(x["po_line_id"], 0) + x["qty_accepted"]
            late = (d["delivered_at"].date() - p["promised_date"]).days
            complete = all(got.get(l["po_line_id"], 0) >= l["quantity"] for l in pol[po_id])
            if d["is_on_time"] != (late <= 0) or d["days_late"] != max(0, late) or d["completes_po"] != complete:
                bad.append(d["delivery_id"])
        seqs = sorted(dels, key=lambda d: d["delivered_at"])
        if [d["delivery_seq"] for d in seqs] != list(range(1, len(dels) + 1)):
            bad.append(po_id + " sequence")
    rep.check("arithmetic", "delivery on-time / days late / completes_po / sequence recompute", len(T["delivery"]), bad)
    bad = []
    for p in T["purchase_order"]:
        st = [l["line_status"] for l in pol[p["po_id"]]]
        expect = ("RECEIVED" if all(s == "RECEIVED" for s in st) else "CLOSED_SHORT" if "CLOSED_SHORT" in st
                  else "PARTIALLY_RECEIVED" if any(l["qty_received"] for l in pol[p["po_id"]]) else "ISSUED")
        if p["status"] != expect:
            bad.append(p["po_id"])
    rep.check("arithmetic", "PO status consistent with line receipt status", len(T["purchase_order"]), bad)


def budget(rep, T) -> None:
    bud, ledger = idx(T["budget"], "budget_id"), T["budget_transaction"]
    sums = {b: [0.0, 0.0, 0.0] for b in bud}
    for t in ledger:
        s = sums[t["budget_id"]]
        s[0] += t["allocated_delta_usd"]
        s[1] += t["reserved_delta_usd"]
        s[2] += t["committed_delta_usd"]
    bad = []
    for bb in T["budget_balance"]:
        tr, res, com = sums[bb["budget_id"]]
        cur = bud[bb["budget_id"]]["allocated_amount_usd"] + tr
        if not (eq(bb["allocated_original_usd"], bud[bb["budget_id"]]["allocated_amount_usd"]) and eq(bb["transfers_net_usd"], tr)
                and eq(bb["allocated_current_usd"], cur) and eq(bb["reserved_usd"], res) and eq(bb["committed_usd"], com)
                and eq(bb["available_usd"], cur - res - com)):
            bad.append(bb["budget_id"])
    rep.check("budget", "budget_balance = allocation + sum of ledger deltas (available = allocated - reserved - committed)",
              len(T["budget_balance"]), bad)
    net = money(sum(t["allocated_delta_usd"] for t in ledger))
    rep.check("budget", "transfers net to zero (contingency out = department in)", 1, [] if eq(net, 0) else [net])
    apr = idx(T["approval"], "approval_id")
    rep.check("budget", "every transfer is backed by an APPROVED budget exception of the same amount",
              sum(1 for t in ledger if t["txn_type"].startswith("TRANSFER")),
              [t["budget_txn_id"] for t in ledger if t["txn_type"].startswith("TRANSFER") and not (
                  t["source_id"] in apr and apr[t["source_id"]]["approval_type"] == "BUDGET_EXCEPTION"
                  and apr[t["source_id"]]["decision"] == "APPROVED" and eq(abs(t["allocated_delta_usd"]), apr[t["source_id"]]["basis_amount_usd"]))])
    held, first = {}, {}
    for t in ledger:
        if t["source_type"] == "PURCHASE_REQUEST":
            held[t["source_id"]] = held.get(t["source_id"], 0.0) + t["reserved_delta_usd"]
            if t["txn_type"] == "RESERVE":
                first[t["source_id"]] = t["reserved_delta_usd"]
    open_states = {"SUBMITTED", "SOURCING", "PENDING_APPROVAL", "APPROVED"}
    prs = T["purchase_request"]
    rep.check("budget", "reservation = estimate at submission; held while open, fully released once ordered/rejected/cancelled",
              len(prs), [p["pr_id"] for p in prs if not eq(first.get(p["pr_id"]), p["estimated_total_usd"])
                         or (p["status"] in open_states) != (held.get(p["pr_id"], 0.0) > 0.005) or held.get(p["pr_id"], 0.0) < -0.005])
    by_pr = {p["pr_id"]: p for p in prs}
    rfq = idx(T["rfq"], "rfq_id")
    adj = {}
    for t in ledger:
        if t["txn_type"] in ("RESERVE", "RESERVE_ADJUST"):
            adj[t["source_id"]] = adj.get(t["source_id"], 0.0) + t["reserved_delta_usd"]
    rep.check("budget", "after award the reservation is re-based to the awarded landed cost", len(T["rfq_award"]),
              [a["rfq_id"] for a in T["rfq_award"] if not eq(adj.get(rfq[a["rfq_id"]]["pr_id"]), a["awarded_landed_cost_usd"])])
    del by_pr
    com = {}
    for t in ledger:
        if t["source_type"] == "PURCHASE_ORDER":
            com[t["source_id"]] = com.get(t["source_id"], 0.0) + t["committed_delta_usd"]
    pol = group(T["po_line"], "po_id")
    bad = []
    for p in T["purchase_order"]:
        release = money(sum((l["quantity"] - l["qty_received"]) * l["unit_price"] for l in pol[p["po_id"]]) * p["fx_rate_to_usd"]) \
            if p["status"] == "CLOSED_SHORT" else 0.0
        if not eq(com.get(p["po_id"]), p["total_usd"] - release):
            bad.append(p["po_id"])
    rep.check("budget", "PO commitment = total_usd, less the open balance released on short close", len(T["purchase_order"]), bad)


def lifecycle(rep, T) -> None:
    events = group(T["status_event"], "entity_id")
    current = [("PURCHASE_REQUEST", p["pr_id"], p["status"], p["status_updated_at"]) for p in T["purchase_request"]]
    current += [("RFQ", q["rfq_id"], q["status"], None) for q in T["rfq"]]
    current += [("SUPPLIER_QUOTE", q["quote_id"], q["status"], None) for q in T["supplier_quote"]]
    current += [("PURCHASE_ORDER", p["po_id"], p["status"], None) for p in T["purchase_order"]]
    missing, broken, last = [], [], []
    for etype, eid, status, updated in current:
        evs = sorted(events.get(eid, ()), key=lambda e: e["event_id"])
        if not evs:
            missing.append(eid)
            continue
        if evs[0]["from_status"] is not None or any(e["entity_type"] != etype for e in evs) or any(
                b["from_status"] != a["to_status"] or b["event_ts"] < a["event_ts"] for a, b in zip(evs, evs[1:])):
            broken.append(eid)
        if evs[-1]["to_status"] != status or (updated and evs[-1]["event_ts"] != updated):
            last.append(eid)
    rep.check("lifecycle", "every request, RFQ, quote and PO has a creation event", len(current), missing)
    rep.check("lifecycle", "event chains are continuous and time-ordered (from_status = previous to_status)", len(current), broken)
    rep.check("lifecycle", "current status (and status_updated_at) = last event", len(current), last)


def acceptance(rep, T, L) -> None:
    prs, approvals = idx(T["purchase_request"], "pr_id"), T["approval"]
    by_pr = group(approvals, "pr_id")
    rep.check("acceptance", "approval tier = threshold band of the approval basis (APR-T1..T4)",
              sum(1 for p in prs.values() if p["approval_tier"]),
              [p["pr_id"] for p in prs.values() if p["approval_tier"] and p["approval_tier"] != tier_for(p["approval_basis_usd"])])
    bad, n = [], 0
    for p in prs.values():
        aps = by_pr.get(p["pr_id"], [])
        if not p["approval_tier"] or any(a["decision"] != "APPROVED" for a in aps):
            continue
        n += 1
        spend = [a for a in aps if a["approval_type"] == "SPEND"]
        for level in TIER_LEVELS[p["approval_tier"]]:
            if not any(a["approval_level"] == level or ROLE_RANK[L.req[a["approver_id"]]["role"]] >= LEVEL_RANK[level] for a in spend):
                bad.append(f"{p['pr_id']} missing {level}")
    rep.check("acceptance", "approval thresholds enforced: completed chains cover every level the tier requires", n, bad)
    rep.check("acceptance", "approvers hold the required authority and never approve their own request", len(approvals),
              [a["approval_id"] for a in approvals if a["approver_id"] == prs[a["pr_id"]]["requester_id"]
               or (a["approval_level"] in LEVEL_RANK and ROLE_RANK[L.req[a["approver_id"]]["role"]] < LEVEL_RANK[a["approval_level"]])
               or (a["approval_level"] == "FINANCE_CONTROLLER" and L.req[a["approver_id"]]["role"] != "FINANCE_CONTROLLER")
               or (a["approval_level"] == "PROCUREMENT_DIRECTOR" and L.req[a["approver_id"]]["role"] != "DIRECTOR")])
    bad = []
    for pr_id, aps in by_pr.items():
        aps = sorted(aps, key=lambda a: a["step_no"])
        if [a["step_no"] for a in aps] != list(range(1, len(aps) + 1)):
            bad.append(pr_id)
        bad += [pr_id for a, b in zip(aps, aps[1:]) if a["decision"] != "APPROVED" or b["requested_at"] != a["decided_at"]]
    rep.check("acceptance", "approval steps are sequential (next step routed when the previous is approved)", len(by_pr), bad)
    rep.check("acceptance", "budget exception approvals exist only for requests that failed the budget check",
              sum(1 for a in approvals if a["approval_type"] == "BUDGET_EXCEPTION"),
              [a["approval_id"] for a in approvals if a["approval_type"] == "BUDGET_EXCEPTION"
               and prs[a["pr_id"]]["budget_check_result"] != "OVER_BUDGET"])
    quotes_by_rfq, inv = group(T["supplier_quote"], "rfq_id"), {(i["rfq_id"], i["supplier_id"]): i for i in T["rfq_supplier"]}
    inv_by_rfq = group(T["rfq_supplier"], "rfq_id")
    rep.check("acceptance", "quotes come from invited suppliers; quotes_received = quotes = QUOTED invitations", len(T["rfq"]),
              [q["rfq_id"] for q in T["rfq"] if q["quotes_received"] != len(quotes_by_rfq.get(q["rfq_id"], []))
               or q["quotes_received"] != sum(1 for i in inv_by_rfq[q["rfq_id"]] if i["response_status"] == "QUOTED")]
              + [q["quote_id"] for q in T["supplier_quote"] if inv.get((q["rfq_id"], q["supplier_id"]), {}).get("response_status") != "QUOTED"])
    serves = {(s["supplier_id"], s["category_code"]) for s in T["supplier_category"]}
    rfqs = idx(T["rfq"], "rfq_id")
    rep.check("acceptance", "invited suppliers serve the category and were ACTIVE without HIGH risk at issue", len(T["rfq_supplier"]),
              [(i["rfq_id"], i["supplier_id"]) for i in T["rfq_supplier"]
               if (i["supplier_id"], prs[rfqs[i["rfq_id"]]["pr_id"]]["category_code"]) not in serves
               or L.status_on(i["supplier_id"], i["invited_at"].date()) != "ACTIVE" or L.risk_on(i["supplier_id"], i["invited_at"].date()) == "HIGH"])
    bad = []
    approved = [a for a in T["rfq_award"] if a["status"] == "APPROVED"]
    for a in approved:
        q = rfqs[a["rfq_id"]]
        kinds = {x["approval_type"] for x in by_pr.get(q["pr_id"], [])}
        if q["sourcing_type"] == "COMPETITIVE" and q["quotes_received"] < q["min_quotes_required"] and "COMPETITION_WAIVER" not in kinds:
            bad.append(a["rfq_id"])
        if q["sourcing_type"] == "SINGLE_SOURCE" and "SINGLE_SOURCE" not in kinds:
            bad.append(a["rfq_id"])
    rep.check("acceptance", "approved competitive awards rest on >= 3 quotes or a waiver; single source has a justification approval",
              len(approved), bad)
    reasons = ([a["approval_id"] for a in approvals if a["decision"] != "PENDING" and not a["decision_reason"]]
               + [q["rfq_id"] for q in T["rfq"] if q["status"] == "CANCELLED" and not q["cancel_reason"]]
               + [e["quote_id"] for e in T["quote_evaluation"] if not e["is_eligible"] and not e["disqualification_reason"]]
               + [x["exception_id"] for x in T["exception_register"] if not x["reason_code"] or not x["reason_text"]]
               + [e["event_id"] for e in T["status_event"] if e["to_status"] in ("CANCELLED", "REJECTED", "CLOSED_SHORT") and not e["reason"]]
               + [a["rfq_id"] for a in T["rfq_award"] if a["award_basis"] in ("DELIVERY_REQUIREMENT", "RISK_MITIGATION", "SOLE_SOURCE")
                  and not a["award_rationale"]])
    rep.check("acceptance", "every exception has a reason: decisions, cancellations, disqualifications, register rows, awards",
              len(approvals) + len(T["exception_register"]), reasons)
    items = L.item
    rep.check("acceptance", "request lines belong to the request category and use the item unit of measure", len(T["request_line"]),
              [l["pr_line_id"] for l in T["request_line"] if items[l["item_id"]]["category_code"] != prs[l["pr_id"]]["category_code"]
               or l["uom"] != items[l["item_id"]]["uom"]])
    bud = idx(T["budget"], "budget_id")
    rep.check("acceptance", "request charged to its department budget of the category budget type", len(prs),
              [p["pr_id"] for p in prs.values() if bud[p["budget_id"]]["department_id"] != p["department_id"]
               or bud[p["budget_id"]]["budget_type"] != L.cat[p["category_code"]]["budget_type"]])
    lines, rfq_by_pr, bad = group(T["request_line"], "pr_id"), {q["pr_id"]: q for q in T["rfq"]}, []
    for p in prs.values():
        if p["estimated_total_usd"] < 10_000:
            route = "DIRECT"
        elif any(items[l["item_id"]]["is_sole_source"] for l in lines[p["pr_id"]]):
            route = "SINGLE_SOURCE_RFQ"
        elif p["priority"] == "CRITICAL" and (p["need_by_date"] - p["submitted_at"].date()).days <= 10:
            route = "SINGLE_SOURCE_RFQ"
        else:
            route = "COMPETITIVE_RFQ"
        q = rfq_by_pr.get(p["pr_id"])
        if p["sourcing_route"] != route or (route == "DIRECT") != (q is None) or (
                q and q["sourcing_type"] != ("SINGLE_SOURCE" if route == "SINGLE_SOURCE_RFQ" else "COMPETITIVE")):
            bad.append(p["pr_id"])
    rep.check("acceptance", "sourcing route follows SRC-1 and an RFQ exists exactly for RFQ routes", len(prs), bad)
