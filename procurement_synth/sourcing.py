"""RFQ planning: invitations, supplier quotes, quote evaluation and award recommendation.

Everything here depends only on inputs and effective-dated master data (supplier status, risk
flags, FX), never on budget state, so it is planned before the process simulation runs.
Supplier responses are external behaviour; the number of responses is allocated so the quote
volume matches the brief exactly, while the award itself is always computed by rules AWD-1..4.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .config import (AS_OF, AWARD_DELIVERY_PREMIUM_MAX, AWARD_RISK_PREMIUM_MAX, MIN_COMPETITIVE_QUOTES)
from .master import World
from .util import (add_business_days, add_work_hours, at, is_workday, line_id, money, next_workday, quote_id,
                   rfq_id, rng, weighted)

VALIDITY_DAYS = [(14, 0.15), (30, 0.5), (45, 0.2), (60, 0.15)]


def plan_sourcing(w: World, prs: list[dict], gt, events: list) -> list[dict]:
    rfq_prs = [p for p in prs if p["sourcing_route"] != "DIRECT"]
    rfqs = [_plan_rfq(w, pr) for pr in rfq_prs]
    _allocate_responses(w, rfqs, w.cfg.scale.quotes)
    for q in rfqs:
        _materialise_quotes(w, q)
    rfqs.sort(key=lambda q: (q["issued_at"], q["pr_id"]))
    for n, q in enumerate(rfqs, 1):
        q["rfq_id"] = rfq_id(n)
        for inv in q["_invites"]:
            inv["rfq_id"] = q["rfq_id"]
    quotes = sorted((qt for q in rfqs for qt in q["_quotes"]), key=lambda qt: (qt["submitted_at"], qt["supplier_id"]))
    for n, qt in enumerate(quotes, 1):
        qt["quote_id"] = quote_id(qt["supplier_id"], n)
        qt["rfq_id"] = qt["_rfq"]["rfq_id"]
        for ln in qt["_lines"]:
            ln["quote_id"] = qt["quote_id"]
            ln["quote_line_id"] = line_id(qt["quote_id"], ln["line_no"])
    for q in rfqs:
        _evaluate(w, q)
    if w.cfg.inject_anomalies:
        _inject_award_anomalies(w, rfqs, gt)
    for q in rfqs:
        _rfq_events(q, events)
    return rfqs


# ------------------------------------------------------------------ planning
def _plan_rfq(w: World, pr: dict) -> dict:
    r = rng(w.seed, "rfq", pr["_key"])
    issued = add_work_hours(pr["submitted_at"], r.uniform(2, 24))
    if issued > AS_OF:                  # requests raised just before the snapshot are issued the same day
        issued = (pr["submitted_at"] + (AS_OF - pr["submitted_at"]) * r.uniform(0.3, 0.9)).replace(second=0, microsecond=0)
    due_day = issued.date() + timedelta(days=r.randint(7, 14))
    while not is_workday(due_day):
        due_day = next_workday(due_day)
    due = at(due_day, 17)
    evaluated = add_work_hours(due, r.uniform(4, 30))
    if r.random() < w.cfg.params.delayed_evaluation_rate:
        evaluated = add_work_hours(evaluated + timedelta(days=r.randint(10, 30)), 1)
    single = pr["sourcing_route"] == "SINGLE_SOURCE_RFQ"
    cat = pr["category_code"]
    pool = sorted(s for s in w.sups_by_cat[cat] if w.usable(s, issued.date()))
    if single:
        oem = next((w.item[ln["item_id"]]["sole_source_supplier_id"] for ln in pr["_lines"]
                    if w.item[ln["item_id"]]["is_sole_source"]), None)
        pref = [sc["supplier_id"] for sc in w.preferred.get(cat, ()) if w.usable(sc["supplier_id"], issued.date())]
        invited = [oem or (pref + pool + sorted(w.sups_by_cat[cat]))[0]]
    else:
        k = min(len(pool), r.randint(4, 6))
        tier_w = {"STRATEGIC": 1.4, "PREFERRED": 1.2, "APPROVED": 1.0}
        keyed = sorted(((r.random() ** (1 / (tier_w[w.sup[s]["supplier_tier"]] * w.sup[s]["_response"])), s)
                        for s in pool), reverse=True)
        invited = [s for _, s in keyed[:k]]
    cancel_at = None
    if pr["_cancel_u"] < w.cfg.params.cancel_rate_rfq:
        cancel_at = issued + (evaluated - issued) * pr["_cancel_frac"]
        cancel_at = add_work_hours(cancel_at, 0.1)
    cutoff = min(AS_OF, cancel_at or AS_OF, due)
    invites = []
    for s in invited:
        rs = rng(w.seed, "invite", pr["_key"], s)
        t = add_work_hours(issued, rs.uniform(2, max(3, (due - issued).days * 7 - 2)))
        invites.append({"rfq_id": None, "supplier_id": s, "invited_at": issued, "response_status": None,
                        "responded_at": None, "_t": min(t, due), "_prop": rs.random() * w.sup[s]["_response"]})
    invites.sort(key=lambda i: -i["_prop"])      # most eager responders first
    return {"rfq_id": None, "pr_id": pr["pr_id"], "_pr": pr, "buyer_id": _buyer(w, pr),
            "sourcing_type": "SINGLE_SOURCE" if single else "COMPETITIVE",
            "single_source_reason": pr["_ss_reason"], "currency_code": "USD", "issued_at": issued,
            "response_due_at": due, "min_quotes_required": 1 if single else MIN_COMPETITIVE_QUOTES,
            "evaluated_at": None, "status": None, "cancel_reason": None, "quotes_received": 0,
            "_planned_eval": evaluated, "_cancel_at": cancel_at, "_cutoff": cutoff, "_invites": invites,
            "_insufficient": (not single) and r.random() < w.cfg.params.insufficient_bids_rate,
            "_quotes": [], "_evals": [], "_award": None, "_n": 0}


def _buyer(w: World, pr: dict) -> str:
    return w.buyers[int(rng(w.seed, "buyer", pr["_key"]).random() * len(w.buyers))]


def _allocate_responses(w: World, rfqs: list[dict], target: int) -> None:
    """Decide how many invited suppliers bid so the total received equals `target`."""
    cap = {}
    for q in rfqs:
        cap[id(q)] = sum(1 for i in q["_invites"] if i["_t"] <= q["_cutoff"])
        base = 1 if q["sourcing_type"] == "SINGLE_SOURCE" else (2 if q["_insufficient"] else MIN_COMPETITIVE_QUOTES)
        q["_n"] = min(cap[id(q)], base)
    extra = target - sum(q["_n"] for q in rfqs)
    r = rng(w.seed, "quote-allocation")
    open_slots = [q for q in rfqs if q["sourcing_type"] == "COMPETITIVE" and not q["_insufficient"]]
    while extra > 0:
        slots = [q for q in open_slots if q["_n"] < min(cap[id(q)], 6)]
        if not slots:
            break
        q = weighted(r, [(q, q["_pr"]["estimated_total_usd"] ** 0.5) for q in slots])
        q["_n"] += 1
        extra -= 1
    while extra < 0:                     # only if the target is below the rule minimum
        q = max(rfqs, key=lambda q: (q["_n"], q["pr_id"]))
        q["_n"] -= 1
        extra += 1


def _materialise_quotes(w: World, q: dict) -> None:
    pr, cat = q["_pr"], w.cat[q["_pr"]["category_code"]]
    responders, received = [], 0
    for inv in q["_invites"]:
        if received < q["_n"] and inv["_t"] <= q["_cutoff"]:
            inv["response_status"], inv["responded_at"] = "QUOTED", inv["_t"]
            responders.append(inv)
            received += 1
        elif inv["_t"] <= q["_cutoff"] and inv["_prop"] > 0.25:
            inv["response_status"], inv["responded_at"] = "DECLINED", inv["_t"]
        elif q["_cancel_at"] is None and q["response_due_at"] > AS_OF:
            inv["response_status"] = "PENDING"
        else:
            inv["response_status"] = "NO_RESPONSE"
    for inv in responders:
        s = w.sup[inv["supplier_id"]]
        r = rng(w.seed, "quote", pr["_key"], s["supplier_id"])
        submitted = inv["_t"]
        currency = s["currency_code"] if s["_local_ccy"] else "USD"
        fx = w.fx_rate(currency, submitted)
        foreign = s["country_code"] != "US"
        incoterm = s["default_incoterm"]
        lead = cat["standard_lead_time_days"] * s["_lead_factor"] * r.uniform(0.85, 1.2)
        if foreign and not cat["is_service"]:
            lead += r.randint(10, 25)
        lines, goods = [], 0.0
        for ln in pr["_lines"]:
            item = w.item[ln["item_id"]]
            vol = 0.92 if ln["quantity"] >= 500 else 0.95 if ln["quantity"] >= 100 else 1.0
            unit_usd = item["list_price_usd"] * s["_price_factor"] * r.uniform(0.94, 1.06) * vol
            if foreign and incoterm == "DDP":
                unit_usd *= 1.08
            unit = money(unit_usd / fx)
            amount = money(unit * ln["quantity"])
            goods += amount
            lines.append({"quote_line_id": None, "quote_id": None, "pr_line_id": ln["pr_line_id"],
                          "line_no": ln["line_no"], "quantity": ln["quantity"], "unit_price": unit,
                          "line_amount": amount, "_item": ln["item_id"]})
        goods = money(goods)
        if cat["is_service"] or incoterm == "DDP":
            freight = 0.0
        else:
            freight = money(goods * (r.uniform(0.04, 0.09) if foreign else r.uniform(0.015, 0.04)))
        q["_quotes"].append({
            "quote_id": None, "rfq_id": None, "supplier_id": s["supplier_id"], "submitted_at": submitted,
            "valid_until": submitted.date() + timedelta(days=weighted(r, VALIDITY_DAYS)), "currency_code": currency,
            "incoterm": incoterm, "lead_time_days": max(1, round(lead)), "goods_amount": goods,
            "freight_amount": freight, "total_amount": money(goods + freight), "status": "RECEIVED",
            "_lines": lines, "_rfq": q})
    q["quotes_received"] = len(q["_quotes"])


# ------------------------------------------------------------------ evaluation & award
def landed_cost(w: World, quote: dict, fx: float) -> tuple[float, float, float, float]:
    """(goods_usd, freight_usd, duty_usd, landed_usd) - duty applies to non-US, non-DDP quotes."""
    sup = w.sup[quote["supplier_id"]]
    cat = w.cat[w.item[quote["_lines"][0]["_item"]]["category_code"]]
    goods = money(quote["goods_amount"] * fx)
    freight = money(quote["freight_amount"] * fx)
    duty = money(goods * cat["import_duty_rate"]) if sup["country_code"] != "US" and quote["incoterm"] != "DDP" else 0.0
    return goods, freight, duty, money(goods + freight + duty)


def _evaluate_quote(w: World, q: dict, qt: dict, when: datetime) -> dict:
    fx = w.fx_rate(qt["currency_code"], qt["submitted_at"])
    goods, freight, duty, landed = landed_cost(w, qt, fx)
    expected = add_business_days(when.date(), 2) + timedelta(days=qt["lead_time_days"])
    status, risk = w.status_on(qt["supplier_id"], when.date()), w.risk_on(qt["supplier_id"], when.date())
    valid = qt["valid_until"] >= when.date()
    reason = None if valid else "EXPIRED"
    if status != "ACTIVE":
        reason = "SUPPLIER_INACTIVE"
    elif risk == "HIGH":
        reason = "SUPPLIER_HIGH_RISK"
    return {"quote_id": qt["quote_id"], "rfq_id": q["rfq_id"], "evaluated_at": when, "fx_rate_used": fx,
            "goods_usd": goods, "freight_usd": freight, "duty_usd": duty, "landed_cost_usd": landed,
            "expected_delivery_date": expected, "meets_need_by": expected <= q["_pr"]["need_by_date"],
            "is_valid_at_evaluation": valid, "supplier_status_at_evaluation": status,
            "supplier_risk_at_evaluation": risk, "is_eligible": reason is None,
            "disqualification_reason": reason, "landed_cost_rank": None, "_quote": qt}


def _rank(evals: list[dict]) -> list[dict]:
    elig = sorted((e for e in evals if e["is_eligible"]), key=lambda e: (e["landed_cost_usd"], e["quote_id"]))
    for e in evals:
        e["landed_cost_rank"] = None
    for n, e in enumerate(elig, 1):
        e["landed_cost_rank"] = n
    return elig


def _evaluate(w: World, q: dict) -> None:
    if q["_cancel_at"] and q["_cancel_at"] <= min(q["_planned_eval"], AS_OF):
        q["cancel_reason"] = "REQUIREMENT_WITHDRAWN"
        return
    if q["_planned_eval"] > AS_OF:
        return
    when = q["evaluated_at"] = q["_planned_eval"]
    q["_evals"] = [_evaluate_quote(w, q, qt, when) for qt in q["_quotes"]]
    elig = _rank(q["_evals"])
    if not elig:
        q["cancel_reason"] = "NO_ELIGIBLE_QUOTES"
        return
    choice, basis, rationale = _select(q, elig)
    q["_award"] = {"rfq_id": q["rfq_id"], "quote_id": choice["quote_id"], "supplier_id": choice["_quote"]["supplier_id"],
                   "buyer_id": q["buyer_id"], "recommended_at": when, "award_basis": basis,
                   "award_rationale": rationale, "awarded_landed_cost_usd": choice["landed_cost_usd"],
                   "status": "PENDING_APPROVAL", "decided_at": None, "_eval": choice}


def _select(q: dict, elig: list[dict]):
    """Award rules AWD-1..4 (documented in docs/business_rules.md)."""
    low = elig[0]
    if q["sourcing_type"] == "SINGLE_SOURCE":
        return low, "SOLE_SOURCE", f"Single source ({q['single_source_reason']}); price reviewed against estimate."
    if low["meets_need_by"]:
        if low["supplier_risk_at_evaluation"] == "MEDIUM":
            alt = next((e for e in elig[1:] if e["supplier_risk_at_evaluation"] in ("NONE", "LOW")
                        and e["meets_need_by"]
                        and e["landed_cost_usd"] <= low["landed_cost_usd"] * (1 + AWARD_RISK_PREMIUM_MAX)), None)
            if alt:
                prem = alt["landed_cost_usd"] / low["landed_cost_usd"] - 1
                return alt, "RISK_MITIGATION", (f"Lowest quote {low['quote_id']} is from a supplier with an open MEDIUM "
                                                f"risk flag; selected {alt['quote_id']} at +{prem:.1%} landed cost.")
        return low, "LOWEST_LANDED_COST", None
    fast = [e for e in elig if e["meets_need_by"]
            and e["landed_cost_usd"] <= low["landed_cost_usd"] * (1 + AWARD_DELIVERY_PREMIUM_MAX)]
    if fast:
        pick = min(fast, key=lambda e: (e["landed_cost_usd"], e["quote_id"]))
        prem = pick["landed_cost_usd"] / low["landed_cost_usd"] - 1
        return pick, "DELIVERY_REQUIREMENT", (
            f"Lowest quote {low['quote_id']} delivers {low['expected_delivery_date']} after the need-by date "
            f"{q['_pr']['need_by_date']}; selected {pick['quote_id']} (on time) at +{prem:.1%} landed cost.")
    return low, "LOWEST_LANDED_COST", None


def _inject_award_anomalies(w: World, rfqs: list[dict], gt) -> None:
    cutoff = AS_OF - timedelta(days=6)
    cands = [q for q in rfqs if q["_award"] and q["sourcing_type"] == "COMPETITIVE"
             and q["_award"]["award_basis"] == "LOWEST_LANDED_COST" and q["evaluated_at"] <= cutoff
             and sum(1 for e in q["_evals"] if e["is_eligible"]) >= 2]
    cands.sort(key=lambda q: q["evaluated_at"])
    exp_pool = [q for q in cands if (q["evaluated_at"].date() - q["_award"]["_eval"]["_quote"]["submitted_at"].date()).days >= 10]
    taken = set()
    for q in _spread(exp_pool, w.cfg.anomaly_quota("QUOTE_EXPIRED_AT_AWARD")):
        taken.add(q["rfq_id"])
        qt = q["_award"]["_eval"]["_quote"]
        r = rng(w.seed, "expire", q["rfq_id"])
        old = qt["valid_until"]
        qt["valid_until"] = max(qt["submitted_at"].date() + timedelta(days=7),
                                q["evaluated_at"].date() - timedelta(days=r.randint(1, 3)))
        ev = q["_award"]["_eval"]
        ev.update({"is_valid_at_evaluation": False, "is_eligible": False, "disqualification_reason": "EXPIRED"})
        _rank(q["_evals"])
        days = (q["evaluated_at"].date() - qt["valid_until"]).days
        gt.add("QUOTE_EXPIRED_AT_AWARD", "AWARDED_AFTER_VALIDITY", "RFQ", q["rfq_id"],
               related=[qt["quote_id"], q["pr_id"]],
               description=f"Quote {qt['quote_id']} expired on {qt['valid_until']} but was selected on "
                           f"{q['evaluated_at']:%Y-%m-%d} ({days} days later) without a validity extension.",
               quote_id=qt["quote_id"], valid_until=str(qt["valid_until"]),
               award_date=f"{q['evaluated_at']:%Y-%m-%d}", days_expired=days, original_validity=str(old))
    nl_pool = [q for q in cands if q["rfq_id"] not in taken]
    for q in _spread(nl_pool, w.cfg.anomaly_quota("NON_LOWEST_AWARD_NO_RATIONALE")):
        elig = [e for e in q["_evals"] if e["is_eligible"]]
        elig.sort(key=lambda e: e["landed_cost_rank"])
        low = elig[0]
        alt = next((e for e in elig[1:] if e["landed_cost_usd"] <= low["landed_cost_usd"] * 1.3), elig[1])
        q["_award"].update({"quote_id": alt["quote_id"], "supplier_id": alt["_quote"]["supplier_id"],
                            "award_basis": None, "award_rationale": None,
                            "awarded_landed_cost_usd": alt["landed_cost_usd"], "_eval": alt})
        prem = alt["landed_cost_usd"] / low["landed_cost_usd"] - 1
        gt.add("NON_LOWEST_AWARD_NO_RATIONALE", "UNEXPLAINED_PREMIUM", "RFQ", q["rfq_id"],
               related=[alt["quote_id"], low["quote_id"], q["pr_id"]],
               description=f"Selected {alt['quote_id']} at {alt['landed_cost_usd']:,.2f} USD landed although eligible "
                           f"{low['quote_id']} was {low['landed_cost_usd']:,.2f} USD (+{prem:.1%}); no basis or rationale recorded.",
               awarded_quote=alt["quote_id"], lowest_quote=low["quote_id"],
               awarded_landed_usd=alt["landed_cost_usd"], lowest_landed_usd=low["landed_cost_usd"],
               premium_pct=round(prem * 100, 2))


def _spread(pool: list, n: int) -> list:
    n = min(n, len(pool))
    return [pool[int((j + 0.5) * len(pool) / n)] for j in range(n)] if n else []


def _rfq_events(q: dict, ev) -> None:
    rid, buyer, pr = q["rfq_id"], q["buyer_id"], q["_pr"]
    ev.add("RFQ", rid, None, "OPEN", q["issued_at"], buyer, f"Issued to {len(q['_invites'])} supplier(s)")
    for qt in q["_quotes"]:
        ev.add("SUPPLIER_QUOTE", qt["quote_id"], None, "RECEIVED", qt["submitted_at"], None, f"Bid for {rid}")
    cancel = q["_cancel_at"] if q["cancel_reason"] == "REQUIREMENT_WITHDRAWN" else None
    state = "OPEN"
    if q["response_due_at"] <= AS_OF and (cancel is None or cancel >= q["response_due_at"]):
        ev.add("RFQ", rid, "OPEN", "UNDER_EVALUATION", q["response_due_at"], None, "Bid deadline reached")
        state = "UNDER_EVALUATION"
    if cancel:
        ev.add("RFQ", rid, state, "CANCELLED", cancel, pr["requester_id"], "REQUIREMENT_WITHDRAWN")
        for qt in q["_quotes"]:
            ev.add("SUPPLIER_QUOTE", qt["quote_id"], "RECEIVED", "CANCELLED", cancel, None, "RFQ cancelled")
        return
    if not q["evaluated_at"]:
        return
    for e in q["_evals"]:
        qt = e["_quote"]
        to = ("SELECTED" if q["_award"] and q["_award"]["quote_id"] == qt["quote_id"]
              else "DISQUALIFIED" if not e["is_eligible"] else "NOT_SELECTED")
        ev.add("SUPPLIER_QUOTE", qt["quote_id"], "RECEIVED", to, q["evaluated_at"], buyer,
               e["disqualification_reason"] or f"Landed cost rank {e['landed_cost_rank']}")
    if q["_award"]:
        ev.add("RFQ", rid, "UNDER_EVALUATION", "AWARD_RECOMMENDED", q["evaluated_at"], buyer,
               f"Recommended {q['_award']['quote_id']}")
    else:
        ev.add("RFQ", rid, "UNDER_EVALUATION", "CANCELLED", q["evaluated_at"], buyer, "NO_ELIGIBLE_QUOTES")
