"""Master and reference data: departments, requesters, categories, items, suppliers, FX.

Rows are plain dicts keyed by the exported column names. Keys starting with "_" are latent
generator parameters (e.g. a supplier's true on-time probability); they drive the simulation
but are stripped on export so that no hidden "answer" leaks into the published tables.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import catalog_data as cd
from .config import AS_OF, APPROVAL_LIMITS_USD, RunConfig
from .util import money, month_key, rate6, rng, weighted

SEVERITY_ORDER = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


class World:
    """Master data plus effective-dated lookups shared by every later stage."""

    def __init__(self, cfg: RunConfig):
        self.cfg = cfg
        self.seed = cfg.seed
        self.departments, self.requesters, self.categories, self.items = [], [], [], []
        self.suppliers, self.supplier_categories, self.supplier_status, self.risk_flags = [], [], [], []
        self.fx_rates, self.budgets = [], []

    # -------------------------------------------------------------- lookups
    def index(self) -> None:
        self.dept = {d["department_id"]: d for d in self.departments}
        self.req = {r["requester_id"]: r for r in self.requesters}
        self.cat = {c["category_code"]: c for c in self.categories}
        self.item = {i["item_id"]: i for i in self.items}
        self.sup = {s["supplier_id"]: s for s in self.suppliers}
        self.items_by_cat, self.sups_by_cat, self.preferred = {}, {}, {}
        for i in self.items:
            self.items_by_cat.setdefault(i["category_code"], []).append(i)
        for sc in self.supplier_categories:
            self.sups_by_cat.setdefault(sc["category_code"], []).append(sc["supplier_id"])
            if sc["preference_rank"]:
                self.preferred.setdefault(sc["category_code"], []).append(sc)
        for v in self.preferred.values():
            v.sort(key=lambda sc: sc["preference_rank"])
        self.status_rows, self.flag_rows = {}, {}
        for h in self.supplier_status:
            self.status_rows.setdefault(h["supplier_id"], []).append(h)
        for f in self.risk_flags:
            self.flag_rows.setdefault(f["supplier_id"], []).append(f)
        self.fx = {(f["currency_code"], f["rate_month"]): f["usd_per_unit"] for f in self.fx_rates}
        self.buyers = [r["requester_id"] for r in self.requesters if r["role"] == "BUYER"]
        self.controllers = [r["requester_id"] for r in self.requesters if r["role"] == "FINANCE_CONTROLLER"]
        self.cfo = next(r["requester_id"] for r in self.requesters if r["role"] == "CFO")
        self.ceo = next(r["requester_id"] for r in self.requesters if r["role"] == "CEO")
        proc = next(d["department_id"] for d in self.departments if d["department_name"] == "Procurement")
        self.procurement_director = next(r["requester_id"] for r in self.requesters
                                         if r["role"] == "DIRECTOR" and r["department_id"] == proc)

    def status_on(self, sid: str, d: date) -> str:
        status = "INACTIVE"
        for h in self.status_rows.get(sid, ()):
            if h["effective_from"] <= d:
                status = h["status"]
        return status

    def risk_on(self, sid: str, d: date) -> str:
        level = "NONE"
        for f in self.flag_rows.get(sid, ()):
            if f["raised_date"] <= d and (f["cleared_date"] is None or d < f["cleared_date"]):
                if SEVERITY_ORDER[f["severity"]] > SEVERITY_ORDER[level]:
                    level = f["severity"]
        return level

    def open_flag_types(self, sid: str, d: date) -> set:
        return {f["flag_type"] for f in self.flag_rows.get(sid, ())
                if f["raised_date"] <= d and (f["cleared_date"] is None or d < f["cleared_date"])}

    def usable(self, sid: str, d: date) -> bool:
        return self.status_on(sid, d) == "ACTIVE" and self.risk_on(sid, d) != "HIGH"

    def fx_rate(self, currency: str, d) -> float:
        return self.fx[(currency, month_key(d))]

    def is_active_employee(self, rid: str, d: date) -> bool:
        r = self.req[rid]
        return r["hire_date"] <= d and (r["termination_date"] is None or d < r["termination_date"])


# ------------------------------------------------------------------ builders
def build_master(cfg: RunConfig) -> World:
    w = World(cfg)
    _departments(w)
    _requesters(w)
    _categories(w)
    _suppliers(w)
    _supplier_lifecycle(w)
    _items(w)
    _fx(w)
    w.index()
    return w


def _departments(w: World) -> None:
    for n, (name, division, demand_w, head_w, affinity) in enumerate(cd.DEPARTMENTS, 1):
        w.departments.append({
            "department_id": f"DEPT-{n:03d}", "department_name": name, "cost_center": f"CC-{1000 + n * 100}",
            "division": division, "status": "ACTIVE", "effective_from": date(2018, 1, 1),
            "_demand_weight": demand_w, "_head_weight": head_w, "_affinity": affinity})


def _requesters(w: World) -> None:
    r = rng(w.seed, "requesters")
    n_total = w.cfg.scale.requesters
    depts = w.departments
    by_name = {d["department_name"]: d["department_id"] for d in depts}
    names = [(f, l) for f in cd.FIRST_NAMES for l in cd.LAST_NAMES]
    r.shuffle(names)
    rows = []

    def add(role, dept_id, title, manager, hired, limit=None):
        first, last = names[len(rows)]
        rows.append({"requester_id": f"EMP-{len(rows) + 1:05d}", "full_name": f"{first} {last}",
                     "email": f"{first.lower()}.{last.lower()}@example.com", "department_id": dept_id,
                     "job_title": title, "role": role, "approval_limit_usd": limit, "manager_id": manager,
                     "hire_date": hired, "termination_date": None, "status": "ACTIVE"})
        return rows[-1]["requester_id"]

    def hired(lo=2010, hi=2025):
        return date(lo, 1, 1) + timedelta(days=r.randrange((date(hi, 12, 31) - date(lo, 1, 1)).days))

    exec_id, fin_id = by_name["Executive Office"], by_name["Finance"]
    ceo = add("CEO", exec_id, "Chief Executive Officer", None, hired(2010, 2016), APPROVAL_LIMITS_USD["CEO"])
    cfo = add("CFO", fin_id, "Chief Financial Officer", ceo, hired(2012, 2019), APPROVAL_LIMITS_USD["CFO"])
    vp = {div: add("VP", exec_id, f"VP {div.title()}", ceo, hired(2012, 2021), APPROVAL_LIMITS_USD["VP"])
          for div in cd.DIVISIONS}
    directors = {}
    for d in depts:
        boss = ceo if d["department_name"] == "Executive Office" else cfo if d["department_id"] == fin_id else vp[d["division"]]
        title = "Chief of Staff" if d["department_name"] == "Executive Office" else f"Director, {d['department_name']}"
        directors[d["department_id"]] = add("DIRECTOR", d["department_id"], title, boss, hired(2012, 2023),
                                            APPROVAL_LIMITS_USD["DIRECTOR"])
    n_buyers = max(2, round(n_total * 8 / 300))
    n_ctrl = max(1, round(n_total * 3 / 300))
    n_mgr = max(len(depts), round(n_total * 46 / 300))
    head_w = {d["department_id"]: d["_head_weight"] for d in depts}
    mgr_counts = _apportion(n_mgr, head_w, minimum=1)
    managers = {}
    for d in depts:
        managers[d["department_id"]] = [
            add("MANAGER", d["department_id"], f"{d['department_name']} Manager", directors[d["department_id"]],
                hired(2012, 2024), APPROVAL_LIMITS_USD["MANAGER"]) for _ in range(mgr_counts[d["department_id"]])]
    proc_id = by_name["Procurement"]
    for i in range(n_buyers):
        add("BUYER", proc_id, "Senior Buyer" if i % 3 == 0 else "Buyer", r.choice(managers[proc_id]), hired(2014, 2025))
    for _ in range(n_ctrl):
        add("FINANCE_CONTROLLER", fin_id, "Financial Controller", r.choice(managers[fin_id]), hired(2014, 2024))
    staff_counts = _apportion(n_total - len(rows), head_w, minimum=0)
    for d in depts:
        for _ in range(staff_counts[d["department_id"]]):
            title = f"{d['department_name'].split(' ')[0].rstrip(',')} {r.choice(cd.STAFF_TITLES)}"
            add("STAFF", d["department_id"], title, r.choice(managers[d["department_id"]]), hired(2014, 2025))
            row = rows[-1]
            u = r.random()
            if u < w.cfg.params.staff_new_hire_rate:
                row["hire_date"] = date(2026, 1, 5) + timedelta(days=r.randrange(250))
            elif u < w.cfg.params.staff_new_hire_rate + w.cfg.params.staff_attrition_rate:
                row["termination_date"] = date(2026, 2, 1) + timedelta(days=r.randrange(260))
                row["status"] = "INACTIVE" if row["termination_date"] <= AS_OF.date() else "ACTIVE"
    w.requesters = rows


def _apportion(total: int, weights: dict, minimum: int) -> dict:
    keys = list(weights)
    base = {k: minimum for k in keys}
    rest = total - minimum * len(keys)
    wsum = sum(weights.values())
    shares = {k: rest * weights[k] / wsum for k in keys}
    for k in keys:
        base[k] += int(shares[k])
    leftover = total - sum(base.values())
    for k in sorted(keys, key=lambda k: shares[k] - int(shares[k]), reverse=True)[:leftover]:
        base[k] += 1
    return base


def _categories(w: World) -> None:
    for code, (name, btype, service, duty, lead, noun, _items) in cd.CATEGORIES.items():
        w.categories.append({"category_code": code, "category_name": name, "budget_type": btype,
                             "is_service": service, "import_duty_rate": duty,
                             "standard_lead_time_days": lead, "_noun": noun})


def _suppliers(w: World) -> None:
    r = rng(w.seed, "suppliers")
    n = w.cfg.scale.suppliers
    cats = [c["category_code"] for c in w.categories]
    nouns = {c["category_code"]: c["_noun"] for c in w.categories}
    services = {c["category_code"] for c in w.categories if c["is_service"]}
    goods = [c for c in cats if c not in services]
    countries = [(c, wgt) for c, _, wgt in cd.COUNTRIES]
    ccy = {c: cur for c, cur, _ in cd.COUNTRIES}
    order = cats[:]
    r.shuffle(order)
    used_names = set()
    seeded_foreign = ["DE", "GB", "CA", "DE", "MX", "GB"]   # guarantees currency diversity at any scale
    for k in range(n):
        sid = f"SUP{k + 1:04d}"
        primary = order[k % len(order)]
        country = "US" if primary in services else weighted(r, countries)
        if k < len(order):              # first pass is domestic: every category has a US contract vendor
            country = "US"
        elif primary not in services and seeded_foreign:
            country = seeded_foreign.pop(0)
        pool = [c for c in (cats if country == "US" else goods) if c != primary]
        same_kind = [c for c in pool if (c in services) == (primary in services)]
        extra = r.sample(same_kind, k=min(len(same_kind), weighted(r, [(0, 0.45), (1, 0.4), (2, 0.15)])))
        while True:
            prefix = r.choice(cd.SUPPLIER_PREFIXES).replace("_", " ")
            name = f"{prefix} {nouns[primary]} {r.choice(cd.COUNTRY_SUFFIX[country])}"
            if name not in used_names:
                used_names.add(name)
                break
        tier = weighted(r, [("STRATEGIC", 0.12), ("PREFERRED", 0.30), ("APPROVED", 0.58)])
        incoterm = r.choice(("DDP", "DAP")) if country == "US" else weighted(
            r, [("FCA", 0.3), ("FOB", 0.25), ("EXW", 0.15), ("DAP", 0.15), ("DDP", 0.15)])
        onboarded = date(2014, 1, 1) + timedelta(days=r.randrange((date(2025, 11, 30) - date(2014, 1, 1)).days))
        w.suppliers.append({
            "supplier_id": sid, "supplier_name": name, "country_code": country, "currency_code": ccy[country],
            "supplier_tier": tier,
            "payment_terms": weighted(r, [("NET30", 0.5), ("NET45", 0.3), ("NET60", 0.2)]),
            "default_incoterm": incoterm, "onboarded_date": onboarded, "status": "ACTIVE", "risk_rating": "NONE",
            "contact_email": f"rfq.{sid.lower()}@example.com",
            "_price_factor": min(1.18, max(0.86, r.gauss(1.0, 0.07))), "_on_time": r.uniform(0.80, 0.98),
            "_partial": r.uniform(0.05, 0.25), "_defect": r.uniform(0.0, 0.04), "_response": r.uniform(0.55, 0.95),
            "_lead_factor": r.uniform(0.8, 1.35),
            "_local_ccy": country != "US" and r.random() < w.cfg.params.foreign_local_currency_rate})
        for code in [primary] + extra:
            w.supplier_categories.append({"supplier_id": sid, "category_code": code, "preference_rank": None,
                                          "contract_discount_pct": None,
                                          "effective_from": onboarded + timedelta(days=r.randrange(60))})
    # coverage: every category needs enough vendors for a 3-quote competition after attrition
    sup = {s["supplier_id"]: s for s in w.suppliers}
    min_per_cat = 6 if n >= 100 else 5
    for code in cats:
        serving = {sc["supplier_id"] for sc in w.supplier_categories if sc["category_code"] == code}
        us_serving = {s for s in serving if sup[s]["country_code"] == "US"}
        candidates = [s["supplier_id"] for s in w.suppliers if s["supplier_id"] not in serving
                      and (s["country_code"] == "US" or code not in services)]
        r.shuffle(candidates)
        candidates.sort(key=lambda s: sup[s]["country_code"] != "US")   # domestic first, stable order
        while (len(serving) < min_per_cat or len(us_serving) < 2) and candidates:
            sid = candidates.pop(0)
            serving.add(sid)
            if sup[sid]["country_code"] == "US":
                us_serving.add(sid)
            w.supplier_categories.append({"supplier_id": sid, "category_code": code, "preference_rank": None,
                                          "contract_discount_pct": None,
                                          "effective_from": sup[sid]["onboarded_date"] + timedelta(days=r.randrange(60))})
    # preferred (contract) suppliers: two US vendors per category, better tiers first
    tier_rank = {"STRATEGIC": 0, "PREFERRED": 1, "APPROVED": 2}
    for code in cats:
        links = [sc for sc in w.supplier_categories if sc["category_code"] == code
                 and sup[sc["supplier_id"]]["country_code"] == "US"]
        links.sort(key=lambda sc: (tier_rank[sup[sc["supplier_id"]]["supplier_tier"]], r.random()))
        for rank, sc in enumerate(links[:2], 1):
            sc["preference_rank"] = rank
            sc["contract_discount_pct"] = round(r.uniform(0.08, 0.15) if rank == 1 else r.uniform(0.04, 0.10), 4)
    w.supplier_categories.sort(key=lambda sc: (sc["supplier_id"], sc["category_code"]))


def _supplier_lifecycle(w: World) -> None:
    """Effective-dated status changes and risk flags (inputs to sourcing decisions)."""
    r = rng(w.seed, "supplier-lifecycle")
    p = w.cfg.params
    rank1 = sorted({sc["supplier_id"] for sc in w.supplier_categories if sc["preference_rank"] == 1})
    all_ids = [s["supplier_id"] for s in w.suppliers]
    n_inactive = max(3, round(len(all_ids) * p.supplier_deactivation_rate))
    n_pref = 3 if w.cfg.scale.suppliers >= 100 else 2
    deactivate = r.sample(rank1, k=min(n_pref, len(rank1)))
    deactivate += r.sample([s for s in all_ids if s not in deactivate], k=max(0, n_inactive - len(deactivate)))
    suspend = r.sample([s for s in all_ids if s not in deactivate],
                       k=max(1, round(len(all_ids) * p.supplier_suspension_rate)))
    rows = []
    for s in w.suppliers:
        sid = s["supplier_id"]
        hist = [(sid, "ACTIVE", s["onboarded_date"], "ONBOARDED")]
        if sid in deactivate:
            start, span = (date(2026, 3, 1), 120) if sid in rank1 else (date(2026, 2, 15), 220)
            hist.append((sid, "INACTIVE", start + timedelta(days=r.randrange(span)),
                         r.choice(("CONTRACT_TERMINATED", "MERGED_ACQUIRED", "COMPLIANCE_FAILURE", "VOLUNTARY_EXIT"))))
        elif sid in suspend:
            start = date(2026, 2, 1) + timedelta(days=r.randrange(200))
            hist.append((sid, "SUSPENDED", start, "COMPLIANCE_REVIEW"))
            hist.append((sid, "ACTIVE", start + timedelta(days=r.randint(20, 60)), "REINSTATED"))
        for i, (s_id, status, frm, reason) in enumerate(hist):
            to = hist[i + 1][2] if i + 1 < len(hist) else None
            rows.append({"status_history_id": None, "supplier_id": s_id, "status": status,
                         "effective_from": frm, "effective_to": to, "reason_code": reason})
    for n, row in enumerate(rows, 1):
        row["status_history_id"] = f"SSH-{n:06d}"
    w.supplier_status = rows
    source = {"FINANCIAL_DISTRESS": "CREDIT_MONITORING", "SANCTIONS_SCREENING_HIT": "SANCTIONS_SCREENING",
              "QUALITY_ISSUE": "QUALITY_AUDIT", "DELIVERY_PERFORMANCE": "SUPPLIER_SCORECARD",
              "CYBER_INCIDENT": "NEWS_MONITORING", "ESG_CONCERN": "NEWS_MONITORING"}
    flags = []
    for s in w.suppliers:
        if r.random() >= p.supplier_risk_flag_rate:
            continue
        for _ in range(weighted(r, [(1, 0.75), (2, 0.25)])):
            ftype = weighted(r, [("DELIVERY_PERFORMANCE", 0.3), ("QUALITY_ISSUE", 0.25), ("FINANCIAL_DISTRESS", 0.2),
                                 ("CYBER_INCIDENT", 0.1), ("ESG_CONCERN", 0.1), ("SANCTIONS_SCREENING_HIT", 0.05)])
            sev = "HIGH" if ftype == "SANCTIONS_SCREENING_HIT" else weighted(
                r, [("LOW", 0.4), ("MEDIUM", 0.42), ("HIGH", 0.18)])
            raised = date(2025, 10, 1) + timedelta(days=r.randrange(385))
            cleared = raised + timedelta(days=r.randint(20, 150))
            flags.append({"risk_flag_id": None, "supplier_id": s["supplier_id"], "flag_type": ftype,
                          "severity": sev, "raised_date": raised,
                          "cleared_date": cleared if cleared <= AS_OF.date() else None, "source": source[ftype]})
    flags.sort(key=lambda f: (f["raised_date"], f["supplier_id"], f["flag_type"]))
    for n, f in enumerate(flags, 1):
        f["risk_flag_id"] = f"SRF-{n:06d}"
    w.risk_flags = flags
    w.status_rows, w.flag_rows = {}, {}
    for h in rows:
        w.status_rows.setdefault(h["supplier_id"], []).append(h)
    for f in flags:
        w.flag_rows.setdefault(f["supplier_id"], []).append(f)
    for s in w.suppliers:   # snapshot columns derived from the effective-dated rows
        s["status"] = w.status_on(s["supplier_id"], AS_OF.date())
        s["risk_rating"] = w.risk_on(s["supplier_id"], AS_OF.date())


def _items(w: World) -> None:
    r = rng(w.seed, "items")
    n = 0
    stable = {s["supplier_id"] for s in w.suppliers
              if all(h["status"] == "ACTIVE" for h in w.status_rows[s["supplier_id"]])
              and all(f["severity"] != "HIGH" for f in w.flag_rows.get(s["supplier_id"], ()))}
    for code, (_n, _b, service, _d, _l, _noun, items) in cd.CATEGORIES.items():
        variants = [("", 1.0)] if service else [("", 1.0), cd.GOODS_VARIANT]
        for name, uom, price in items:
            for label, mult in variants:
                n += 1
                w.items.append({"item_id": f"ITM-{n:05d}", "item_name": f"{name} {label}".strip(),
                                "category_code": code, "uom": uom, "list_price_usd": money(price * mult),
                                "is_sole_source": False, "sole_source_supplier_id": None})
        oem_pool = sorted(sc["supplier_id"] for sc in w.supplier_categories
                          if sc["category_code"] == code and sc["supplier_id"] in stable)
        if service or not oem_pool:
            continue
        base_name, uom, price = r.choice(items)
        n += 1
        w.items.append({"item_id": f"ITM-{n:05d}", "item_name": f"{base_name} - OEM Certified",
                        "category_code": code, "uom": uom, "list_price_usd": money(price * 1.25),
                        "is_sole_source": True, "sole_source_supplier_id": r.choice(oem_pool)})


def _fx(w: World) -> None:
    r = rng(w.seed, "fx")
    for cur, base in cd.FX_BASE.items():
        rate = base
        for m in range(1, 13):
            if cur != "USD" and m > 1:
                rate *= 1 + r.gauss(0, 0.012)
            w.fx_rates.append({"currency_code": cur, "rate_month": f"2026-{m:02d}", "usd_per_unit": rate6(rate)})
