"""Purchase requests and request lines (the demand inputs).

Inputs are sampled; outcomes are not decided here.  The only quota is the demand mix:
exactly `scale.rfqs` requests are generated in the competitive value band, because RFQ
creation is a pure rule on the estimate (SRC-1) and the brief asks for an exact RFQ volume.
Duplicate requests and split purchases are injected here (labelled) when anomalies are on.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import catalog_data as cd
from .config import AS_OF, COMPETITIVE_THRESHOLD_USD, DUPLICATE_WINDOW_DAYS, PERIOD_START
from .master import World
from .util import (add_business_days, add_work_hours, is_workday, lognormal_between, money, pr_id,
                   rng, line_id, weighted, work_time_on)

MONTH_WEIGHT = {1: 0.8, 2: 1.0, 3: 1.2, 4: 0.95, 5: 1.0, 6: 1.15, 7: 0.85, 8: 0.85, 9: 1.15, 10: 1.0}
WEEKDAY_WEIGHT = (1.1, 1.15, 1.1, 1.0, 0.75)
ROLE_FACTOR = {"STAFF": 1.0, "MANAGER": 0.9, "DIRECTOR": 0.45, "BUYER": 0.3, "FINANCE_CONTROLLER": 0.3,
               "VP": 0.12, "CFO": 0.0, "CEO": 0.0}     # CEO/CFO do not raise requests (no self-approval)
COMPETITIVE_PROPENSITY = {"LAB_EQ": 3.0, "IT_HW": 2.2, "PRO_SVC": 2.2, "MKT_SVC": 2.0, "RAW_MAT": 1.8,
                          "FURN": 1.6, "SW_LIC": 1.6, "ELEC": 1.2, "LOG_SVC": 1.2, "FAC_SVC": 1.2,
                          "PACK": 1.0, "MRO": 0.8, "SAFETY": 0.6, "OFF_SUP": 0.25}
QTY_CAP = {"EA": 400, "BOX": 800, "PK": 800, "KG": 25000, "ROLL": 600, "LIC": 1500, "HR": 2000}
SPLIT_CATEGORIES = ("OFF_SUP", "MRO", "SAFETY", "ELEC", "PACK", "IT_HW")


def build_demand(w: World, gt) -> list[dict]:
    cfg = w.cfg
    planned = cfg.with_(inject_anomalies=True)   # the baseline keeps exactly the non-injected requests
    n_dup = planned.anomaly_quota("DUPLICATE_REQUEST")
    split_sizes = [weighted(rng(w.seed, "split-size", g), [(2, 0.6), (3, 0.4)])
                   for g in range(planned.anomaly_quota("SPLIT_PURCHASE"))]
    n_base = cfg.scale.requests - n_dup - sum(split_sizes)
    if not cfg.inject_anomalies:
        n_dup, split_sizes = 0, []
    stamps = _submission_times(w, n_base)
    prs = [{"_key": f"B{k:05d}", "submitted_at": t} for k, t in enumerate(stamps)]
    _assign_people_and_categories(w, prs)
    competitive = _choose_competitive(w, prs, cfg.scale.rfqs)
    for pr in prs:
        _fill_request(w, pr, pr["_key"] in competitive)
    if n_dup:
        prs += _inject_duplicates(w, prs, n_dup, gt)
    if split_sizes:
        prs += _inject_splits(w, prs, split_sizes, gt)
    prs.sort(key=lambda p: (p["submitted_at"], p["_key"]))
    for n, pr in enumerate(prs, 1):
        pr["pr_id"] = pr_id(n)
        for ln in pr["_lines"]:
            ln["pr_id"] = pr["pr_id"]
            ln["pr_line_id"] = line_id(pr["pr_id"], ln["line_no"])
    gt.resolve_pr_keys({pr["_key"]: pr["pr_id"] for pr in prs})
    return prs


# ------------------------------------------------------------------ inputs
def _submission_times(w: World, n: int) -> list:
    r = rng(w.seed, "submission-days")
    days, weights = [], []
    d = PERIOD_START
    while d <= AS_OF.date():
        if is_workday(d):
            days.append(d)
            weights.append(MONTH_WEIGHT[d.month] * WEEKDAY_WEIGHT[d.weekday()])
        d += timedelta(days=1)
    chosen = r.choices(days, weights=weights, k=n)
    stamps = sorted(work_time_on(rng(w.seed, "submit-time", k), day) for k, day in enumerate(chosen))
    return [min(s, AS_OF - timedelta(minutes=5)) for s in stamps]


def _assign_people_and_categories(w: World, prs: list[dict]) -> None:
    """Requester and category per request; no requester repeats a category within the
    duplicate window, so duplicate / split patterns only exist where they are injected."""
    dept_size = {}
    for rq in w.requesters:
        dept_size[rq["department_id"]] = dept_size.get(rq["department_id"], 0) + 1
    base_w = {rq["requester_id"]: ROLE_FACTOR[rq["role"]] * w.dept[rq["department_id"]]["_demand_weight"]
              / dept_size[rq["department_id"]] ** 0.5 for rq in w.requesters}
    last_seen = {}
    for pr in prs:
        r = rng(w.seed, "pr-who", pr["_key"])
        d = pr["submitted_at"].date()
        pool = [(rid, wt) for rid, wt in base_w.items() if w.is_active_employee(rid, d)]
        for _ in range(40):
            rid = weighted(r, pool)
            dept = w.req[rid]["department_id"]
            cat = weighted(r, list(w.dept[dept]["_affinity"].items()))
            prev = last_seen.get((rid, cat))
            if prev is None or (d - prev).days > DUPLICATE_WINDOW_DAYS + 2:
                break
        last_seen[(rid, cat)] = d
        pr.update({"requester_id": rid, "department_id": dept, "category_code": cat})


def _choose_competitive(w: World, prs: list[dict], n: int) -> set:
    keyed = []
    for pr in prs:
        u = rng(w.seed, "band", pr["_key"]).random()
        keyed.append((u ** (1.0 / COMPETITIVE_PROPENSITY[pr["category_code"]]), pr["_key"]))
    keyed.sort(reverse=True)            # weighted sampling without replacement
    return {k for _, k in keyed[:n]}


def _fill_request(w: World, pr: dict, competitive: bool) -> None:
    r = rng(w.seed, "pr-body", pr["_key"])
    p = w.cfg.params
    cat = w.cat[pr["category_code"]]
    items = [i for i in w.items_by_cat[cat["category_code"]] if not i["is_sole_source"]]
    oem = [i for i in w.items_by_cat[cat["category_code"]] if i["is_sole_source"]]
    n_lines = weighted(r, [(1, 0.6), (2, 0.4)] if cat["is_service"] else
                       [(1, 0.38), (2, 0.28), (3, 0.17), (4, 0.11), (5, 0.06)])
    chosen = r.sample(items, k=min(n_lines, len(items)))
    if competitive and oem and r.random() < p.sole_source_item_rate:
        chosen = [oem[0]] + chosen[: max(0, len(chosen) - 1)]
    target = (lognormal_between(r, 32_000, 0.85, COMPETITIVE_THRESHOLD_USD * 1.02, 450_000) if competitive
              else lognormal_between(r, 2_200, 0.9, 120, COMPETITIVE_THRESHOLD_USD * 0.97))
    shares = [r.uniform(0.4, 1.6) for _ in chosen]
    lines = []
    for n, (item, share) in enumerate(zip(chosen, shares), 1):
        price = money(item["list_price_usd"] * r.uniform(0.96, 1.14))
        qty = max(1, min(QTY_CAP[item["uom"]], round(target * share / sum(shares) / price)))
        lines.append({"line_no": n, "item_id": item["item_id"], "quantity": qty, "uom": item["uom"],
                      "est_unit_price_usd": price})
    _fit_band(lines, competitive)
    for ln in lines:
        ln["est_line_total_usd"] = money(ln["quantity"] * ln["est_unit_price_usd"])
    pr["_lines"] = lines
    pr["estimated_total_usd"] = money(sum(ln["est_line_total_usd"] for ln in lines))
    pr["priority"] = weighted(r, list(p.priority_weights))
    lead = cat["standard_lead_time_days"]
    urgent = pr["priority"] == "CRITICAL" and competitive and r.random() < 0.5
    if urgent:
        slack = r.randint(4, p.emergency_need_days - 1)
    else:
        sourcing = r.randint(18, 32) if competitive else r.randint(2, 6)
        slack = lead + sourcing + {"LOW": r.randint(15, 60), "MEDIUM": r.randint(8, 40),
                                   "HIGH": r.randint(3, 20), "CRITICAL": r.randint(0, 8)}[pr["priority"]]
    pr["need_by_date"] = add_business_days(pr["submitted_at"].date(), max(2, round(slack * 5 / 7)))
    if r.random() < p.missing_justification_rate:
        pr["justification"] = None
    else:
        item_name = w.item[lines[0]["item_id"]]["item_name"]
        tpl = r.choice(cd.JUSTIFICATIONS)
        quarter = f"Q{(pr['submitted_at'].month - 1) // 3 + 1}"
        pr["justification"] = tpl.format(item=item_name, dept=w.dept[pr["department_id"]]["department_name"],
                                         quarter=quarter)
    pr["_cancel_u"] = r.random()            # requester withdrawal is an external input event
    pr["_cancel_hours"] = r.uniform(3, 70)
    pr["_cancel_frac"] = r.uniform(0.15, 0.95)
    _route(w, pr)


def _fit_band(lines: list[dict], competitive: bool) -> None:
    def total():
        return sum(ln["quantity"] * ln["est_unit_price_usd"] for ln in lines)

    for _ in range(200):
        t = total()
        if competitive and t < COMPETITIVE_THRESHOLD_USD:
            big = max(lines, key=lambda ln: ln["est_unit_price_usd"])
            big["quantity"] += max(1, int((COMPETITIVE_THRESHOLD_USD - t) / big["est_unit_price_usd"]) + 1)
        elif not competitive and t >= COMPETITIVE_THRESHOLD_USD * 0.99:
            big = max(lines, key=lambda ln: ln["quantity"] * ln["est_unit_price_usd"])
            if big["quantity"] > 1:
                big["quantity"] = max(1, int(big["quantity"] * 0.7))
            elif len(lines) > 1:
                lines.remove(big)
                for n, ln in enumerate(lines, 1):
                    ln["line_no"] = n
            else:
                big["est_unit_price_usd"] = money(big["est_unit_price_usd"] * 0.8)
        else:
            return


def _inject_duplicates(w: World, prs: list[dict], n: int, gt) -> list[dict]:
    """DUPLICATE_REQUEST: the requester re-submits an identical direct-buy request."""
    cutoff = AS_OF - timedelta(days=15)
    pool = sorted((p for p in prs if p["sourcing_route"] == "DIRECT" and p["justification"]
                   and p["_cancel_u"] >= w.cfg.params.cancel_rate_direct and p["submitted_at"] < cutoff),
                  key=lambda p: (p["submitted_at"], p["_key"]))
    out = []
    for j in range(n):
        orig = pool[int((j + 0.5) * len(pool) / n)]
        r = rng(w.seed, "dup", orig["_key"])
        dup = {k: v for k, v in orig.items() if k != "_lines"}
        dup.update({"_key": f"D{j:03d}", "_cancel_u": 1.0,
                    "submitted_at": add_work_hours(orig["submitted_at"], r.uniform(3, 45)),
                    "_lines": [dict(ln) for ln in orig["_lines"]]})
        sub = "EXACT_RESUBMISSION"
        if r.random() < 0.35:
            dup["justification"] = orig["justification"].rstrip(".") + " (resubmitted)."
            sub = "REWORDED_RESUBMISSION"
        hours = (dup["submitted_at"] - orig["submitted_at"]).total_seconds() / 3600
        gt.add("DUPLICATE_REQUEST", sub, "PURCHASE_REQUEST", "@" + dup["_key"], related=["@" + orig["_key"]],
               description=f"Request repeats @{orig['_key']} (same requester, category, items and quantities) "
                           f"{hours:.0f}h later.",
               original_pr="@" + orig["_key"], estimated_total_usd=dup["estimated_total_usd"],
               hours_after_original=round(hours, 1))
        out.append(dup)
    return out


def _inject_splits(w: World, prs: list[dict], sizes: list[int], gt) -> list[dict]:
    """SPLIT_PURCHASE: one need split into 2-3 requests that each stay under the $5,000 tier."""
    seen = {}
    for p in prs:
        seen.setdefault((p["requester_id"], p["category_code"]), []).append(p["submitted_at"].date())
    first, last = PERIOD_START + timedelta(days=20), AS_OF.date() - timedelta(days=25)
    out = []
    for g, k in enumerate(sizes):
        r = rng(w.seed, "split", g)
        anchor = first + timedelta(days=int((g + 0.5) * (last - first).days / len(sizes)))
        while not is_workday(anchor):
            anchor += timedelta(days=1)
        staff = sorted(q["requester_id"] for q in w.requesters
                       if q["role"] == "STAFF" and w.is_active_employee(q["requester_id"], anchor)
                       and w.is_active_employee(q["requester_id"], anchor + timedelta(days=10)))
        for _ in range(200):
            rid = r.choice(staff)
            dept = w.req[rid]["department_id"]
            cats = [c for c in SPLIT_CATEGORIES if c in w.dept[dept]["_affinity"]] or list(SPLIT_CATEGORIES)
            cat = r.choice(cats)
            if all(abs((d - anchor).days) > DUPLICATE_WINDOW_DAYS + 4 for d in seen.get((rid, cat), ())):
                break
        seen.setdefault((rid, cat), []).append(anchor)
        total = r.uniform(5_600, 9_600) if k == 2 else r.uniform(7_500, 14_000)
        pool = sorted((i for i in w.items_by_cat[cat] if not i["is_sole_source"]), key=lambda i: i["list_price_usd"])
        item = r.choice([i for i in pool if i["list_price_usd"] <= total / (k * 5)] or pool[:2])
        price = money(item["list_price_usd"] * r.uniform(0.98, 1.10))
        shares = [r.uniform(0.8, 1.2) for _ in range(k)]
        qtys = [max(1, int(total * s / sum(shares) / price)) for s in shares]
        for i in range(k):       # each part under the tier, and parts never identical (identical = duplicate)
            while qtys[i] > 1 and qtys[i] * price >= 4_950:
                qtys[i] -= 1
            while qtys[i] in qtys[:i]:
                qtys[i] += -1 if qtys[i] > 1 else 1
        t = work_time_on(r, anchor)
        need_by = add_business_days(anchor, r.randint(12, 25))
        just = (f"Stock for {w.dept[dept]['department_name']} - {item['item_name']} "
                f"({['first', 'second', 'third'][0]} batch).")
        keys = []
        for i, q in enumerate(qtys):
            key = f"S{g:02d}{chr(97 + i)}"
            keys.append(key)
            line = {"line_no": 1, "item_id": item["item_id"], "quantity": q, "uom": item["uom"],
                    "est_unit_price_usd": price, "est_line_total_usd": money(q * price)}
            out.append({"_key": key, "submitted_at": t, "requester_id": rid, "department_id": dept,
                        "category_code": cat, "_lines": [line], "estimated_total_usd": line["est_line_total_usd"],
                        "priority": "MEDIUM", "need_by_date": need_by,
                        "justification": just.replace("first", ["first", "second", "third"][i]),
                        "_cancel_u": 1.0, "_cancel_hours": 0.0, "_cancel_frac": 0.0,
                        "sourcing_route": "DIRECT", "_ss_reason": None})
            t = add_work_hours(t, r.uniform(2, 20))
        combined = money(sum(q * price for q in qtys))
        gt.add("SPLIT_PURCHASE", "THRESHOLD_AVOIDANCE", "PURCHASE_REQUEST", "@" + keys[0],
               related=["@" + x for x in keys[1:]],
               description=f"{k} requests for {item['item_name']} by the same requester within days; each is "
                           f"below the $5,000 tier-2 approval threshold but together they total ${combined:,.2f}.",
               part_values_usd=[money(q * price) for q in qtys], combined_usd=combined,
               avoided_threshold="APR-T2 (5,000 USD)" if combined < COMPETITIVE_THRESHOLD_USD
               else "APR-T2 (5,000 USD) and SRC-1 RFQ (10,000 USD)")
    return out


def _route(w: World, pr: dict) -> None:
    """Rule SRC-1 (sourcing route) - derived from the estimate, items and need-by date."""
    if pr["estimated_total_usd"] < COMPETITIVE_THRESHOLD_USD:
        pr["sourcing_route"], pr["_ss_reason"] = "DIRECT", None
    elif any(w.item[ln["item_id"]]["is_sole_source"] for ln in pr["_lines"]):
        pr["sourcing_route"], pr["_ss_reason"] = "SINGLE_SOURCE_RFQ", "SOLE_SOURCE_OEM"
    elif pr["priority"] == "CRITICAL" and (pr["need_by_date"] - pr["submitted_at"].date()).days <= w.cfg.params.emergency_need_days:
        pr["sourcing_route"], pr["_ss_reason"] = "SINGLE_SOURCE_RFQ", "EMERGENCY"
    else:
        pr["sourcing_route"], pr["_ss_reason"] = "COMPETITIVE_RFQ", None
