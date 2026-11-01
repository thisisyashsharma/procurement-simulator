"""PO issue (direct contract buys and RFQ awards), delivery planning and goods receipt."""
from __future__ import annotations

from datetime import timedelta

from . import catalog_data as cd
from .util import (add_work_hours, delivery_id, is_workday, line_id, money, next_workday, po_id as fmt_po_id,
                   rng, weighted, work_time_on)

FX_MISMATCH_CCY = ("EUR", "GBP", "CAD", "MXN")


class OrdersMixin:
    # ---------------------------------------------------------------- issue
    def on_po_run(self) -> None:
        """Weekly buyer run: consolidate approved direct buys per contract supplier and budget."""
        if not self.pool:
            return
        groups = {}
        for st in sorted(self.pool, key=lambda s: s["pr"]["pr_id"]):
            pr = st["pr"]
            sup, _ = self.direct_supplier(pr["category_code"])
            groups.setdefault((sup, pr["budget_id"]), []).append(st)
        self.pool = []
        for _, sts in sorted(groups.items()):
            self.issue_direct(sts)

    def on_po_issue(self, st) -> None:
        if st["cancelled"] or st["po"]:
            return
        if not st["rfq"]:
            self.issue_direct([st])
        elif self.w.status_on(st["rfq"]["_award"]["supplier_id"], self.now.date()) != "ACTIVE":
            self.withdraw_award(st)
        else:
            self.issue_rfq_po(st)

    def withdraw_award(self, st) -> None:
        """Awarded supplier deactivated between award and PO: no PO may be issued (CTL-SUP)."""
        rfq, award = st["rfq"], st["rfq"]["_award"]
        st["cancelled"] = True
        rfq["cancel_reason"] = "AWARDED_SUPPLIER_INACTIVE"
        rfq["_withdrawn_at"] = self.now
        award["status"] = "WITHDRAWN"
        self.ev.add("RFQ", rfq["rfq_id"], "AWARDED", "CANCELLED", self.now, rfq["buyer_id"], "AWARDED_SUPPLIER_INACTIVE")
        self.ev.add("SUPPLIER_QUOTE", award["quote_id"], "AWARDED", "CANCELLED", self.now, rfq["buyer_id"],
                    "Supplier no longer active")
        self.ledger.release(st["pr"], self.now, "Award withdrawn: supplier inactive")
        self.set_status(st, "CANCELLED", rfq["buyer_id"], "AWARDED_SUPPLIER_INACTIVE")

    def on_early_po(self, st) -> None:
        """Anomaly PO_WITHOUT_APPROVAL: the buyer releases the PO while approval is still running."""
        if st["cancelled"] or st["po"] or st["status"] != "PENDING_APPROVAL":
            st["early_po"] = False
            if st["status"] == "APPROVED" and not st["po"]:
                self.on_po_issue(st)
            return
        pending = [a for a in self.approvals if a["_st"] is st and a["decision"] == "PENDING"]
        po = self.issue_rfq_po(st) if st["rfq"] else self.issue_direct([st])
        st["gt_row"] = self.gt.add(
            "PO_WITHOUT_APPROVAL", "ISSUED_BEFORE_APPROVAL", "PURCHASE_ORDER", po["po_id"],
            related=[st["pr"]["pr_id"]] + [a["approval_id"] for a in pending],
            description=f"{po['po_id']} issued at {po['issued_at']} while approval step(s) "
                        f"{', '.join(a['approval_id'] for a in pending)} were still pending.",
            pr_id=st["pr"]["pr_id"], po_issued_at=str(po["issued_at"]),
            pending_steps=[a["approval_id"] for a in pending], approval_tier=st["pr"]["approval_tier"])

    def direct_supplier(self, cat: str):
        """Contract supplier for a direct buy: rank 1, else rank 2, else any usable domestic vendor."""
        w, d = self.w, self.now.date()
        for sc in w.preferred.get(cat, ()):
            if w.usable(sc["supplier_id"], d):
                return sc["supplier_id"], sc["contract_discount_pct"]
        pool = sorted(s for s in w.sups_by_cat[cat] if w.usable(s, d))
        domestic = [s for s in pool if w.sup[s]["country_code"] == "US"]
        return (domestic or pool)[0], 0.0

    def issue_direct(self, sts: list) -> dict:
        """Direct contract PO. Lines are priced at list price less the supplier's contract discount
        for the line's category (0 when the vendor holds no contract for that category)."""
        w = self.w
        cats = sorted({s["pr"]["category_code"] for s in sts})
        sup, _ = self.direct_supplier(cats[0])
        prefs = w.preferred.get(cats[0], ())
        stale = prefs[0] if prefs and len(cats) == 1 else None
        inactive = None
        if stale and w.status_on(stale["supplier_id"], self.now.date()) == "INACTIVE" \
                and self.plan.chance("INACTIVE_SUPPLIER", [s["pr"]["pr_id"] for s in sts]):
            inactive = stale
            sup = stale["supplier_id"]
        disc = {sc["category_code"]: sc["contract_discount_pct"] or 0.0
                for sc in w.supplier_categories if sc["supplier_id"] == sup}
        lines = []
        for st in sts:
            for ln in st["pr"]["_lines"]:
                item = w.item[ln["item_id"]]
                price = money(item["list_price_usd"] * (1 - disc.get(item["category_code"], 0.0)))
                lines.append({"pr_id": st["pr"]["pr_id"], "pr_line_id": ln["pr_line_id"], "quote_line_id": None,
                              "item_id": ln["item_id"], "quantity": ln["quantity"], "unit_price": price})
        lead = max(1, round(max(w.cat[c]["standard_lead_time_days"] for c in cats) * w.sup[sup]["_lead_factor"]))
        cat = cats[0]
        buyer = w.buyers[int(rng(w.seed, "buyer", sts[0]["pr"]["_key"]).random() * len(w.buyers))]
        po = self.make_po(sts, sup, "DIRECT_CONTRACT", lines, "USD", 0.0, w.sup[sup]["default_incoterm"], lead,
                          None, None, buyer)
        if inactive:
            since = max(h["effective_from"] for h in w.status_rows[sup] if h["effective_from"] <= self.now.date())
            self.gt.add("INACTIVE_SUPPLIER", "STALE_CONTRACT_SUPPLIER", "PURCHASE_ORDER", po["po_id"],
                        related=[sup] + [s["pr"]["pr_id"] for s in sts],
                        description=f"{po['po_id']} issued to {sup}, INACTIVE since {since}, instead of the active "
                                    f"contract supplier.",
                        supplier_id=sup, inactive_since=str(since), po_issued_at=str(po["issued_at"]),
                        should_have_used=self.direct_supplier(cat)[0])
        return po

    def issue_rfq_po(self, st) -> dict:
        rfq = st["rfq"]
        award = rfq["_award"]
        qt = award["_eval"]["_quote"]
        currency, mismatch = qt["currency_code"], False
        if currency in FX_MISMATCH_CCY and self.plan.chance("QUOTE_CURRENCY_MISMATCH", st["pr"]["pr_id"]):
            currency, mismatch = "USD", True
        lines = [{"pr_id": st["pr"]["pr_id"], "pr_line_id": ql["pr_line_id"], "quote_line_id": ql["quote_line_id"],
                  "item_id": ql["_item"], "quantity": ql["quantity"], "unit_price": ql["unit_price"]}
                 for ql in qt["_lines"]]
        po = self.make_po([st], qt["supplier_id"], "RFQ_AWARD", lines, currency, qt["freight_amount"],
                          qt["incoterm"], qt["lead_time_days"], rfq["rfq_id"], qt["quote_id"], rfq["buyer_id"])
        if mismatch:
            true_usd = money(qt["total_amount"] * self.w.fx_rate(qt["currency_code"], self.now))
            self.gt.add("QUOTE_CURRENCY_MISMATCH", "QUOTE_PRICES_KEYED_AS_USD", "PURCHASE_ORDER", po["po_id"],
                        related=[qt["quote_id"], rfq["rfq_id"], st["pr"]["pr_id"]],
                        description=f"Quote {qt['quote_id']} is priced in {qt['currency_code']} but {po['po_id']} was "
                                    f"issued in USD with the same unit prices.",
                        quote_currency=qt["currency_code"], po_currency="USD", po_total=po["total_amount"],
                        po_total_usd=po["total_usd"], correct_total_usd=true_usd,
                        misstatement_usd=money(po["total_usd"] - true_usd))
        return po

    def make_po(self, sts, supplier_id, source, lines, currency, freight, incoterm, lead, rfq_id, quote_id, buyer):
        w, now = self.w, self.now
        pid = fmt_po_id(len(self.pos) + 1)
        fx = w.fx_rate(currency, now)
        for n, ln in enumerate(lines, 1):
            ln.update(po_line_id=line_id(pid, n), po_id=pid, line_no=n,
                      line_amount=money(ln["quantity"] * ln["unit_price"]), qty_received=0, line_status="OPEN")
        goods = money(sum(ln["line_amount"] for ln in lines))
        total = money(goods + freight)
        cat = w.cat[w.item[lines[0]["item_id"]]["category_code"]]
        foreign = w.sup[supplier_id]["country_code"] != "US"
        duty = money(money(goods * fx) * cat["import_duty_rate"]) if foreign and incoterm != "DDP" else 0.0
        po = {"po_id": pid, "supplier_id": supplier_id, "department_id": sts[0]["pr"]["department_id"],
              "budget_id": sts[0]["pr"]["budget_id"], "buyer_id": buyer, "source_type": source, "rfq_id": rfq_id,
              "quote_id": quote_id, "issued_at": now, "currency_code": currency,
              "payment_terms": w.sup[supplier_id]["payment_terms"], "incoterm": incoterm,
              "promised_date": now.date() + timedelta(days=lead), "goods_amount": goods, "freight_amount": money(freight),
              "total_amount": total, "fx_rate_to_usd": fx, "est_duty_usd": duty,
              "total_usd": money(money(total * fx) + duty), "status": "ISSUED", "closed_at": None,
              "_lines": lines, "_sts": sts, "_n_deliveries": 0}
        self.pos.append(po)
        self.po_lines.extend(lines)
        for st in sts:
            self.ledger.release(st["pr"], now, f"Converted to {pid}")
        self.ledger.commit(po, now)
        self.ev.add("PURCHASE_ORDER", pid, None, "ISSUED", now, buyer, f"{source} {quote_id or ''}".strip())
        for st in sts:
            st["po"] = pid
            self.set_status(st, "ORDERED", buyer, pid)
        self.plan_deliveries(po)
        return po

    # ---------------------------------------------------------------- deliveries
    def plan_deliveries(self, po: dict) -> None:
        """Supplier behaviour (latent on-time / partial / defect rates, worsened by open risk flags)."""
        w = self.w
        sup = w.sup[po["supplier_id"]]
        r = rng(w.seed, "delivery", po["_sts"][0]["pr"]["_key"], po["source_type"])
        flags = w.open_flag_types(po["supplier_id"], self.now.date())
        p_on_time = sup["_on_time"] - (0.2 if "DELIVERY_PERFORMANCE" in flags else 0.0)
        defect = sup["_defect"] + (0.05 if "QUALITY_ISSUE" in flags else 0.0)
        delay = -r.randint(0, 2) if r.random() < p_on_time else min(35, 1 + int(r.expovariate(1 / 6)))
        day = max(self.now.date() + timedelta(days=1), po["promised_date"] + timedelta(days=delay))
        remaining = {ln["po_line_id"]: ln["quantity"] for ln in po["_lines"]}
        partial = (any(q >= 2 for q in remaining.values())
                   and r.random() < sup["_partial"] * w.cfg.params.partial_delivery_rate_scale)
        n_ship = (2 if r.random() < 0.7 else 3) if partial else 1
        shipments = []
        for k in range(n_ship):
            qtys = {}
            for lid, q in remaining.items():
                if q <= 0:
                    continue
                qtys[lid] = q if k == n_ship - 1 or q < 2 else max(1, round(q * r.uniform(0.4, 0.8)))
            qtys = {lid: q for lid, q in qtys.items() if q > 0}
            if qtys:
                shipments.append([day, qtys])
                for lid, q in qtys.items():
                    remaining[lid] -= q
            day += timedelta(days=r.randint(3, 15))
        short = partial and len(shipments) > 1 and r.random() < 0.25
        if short:
            shipments.pop()
        planned = []
        rejected_total = {}
        for day, qtys in shipments:
            rows = []
            for lid, q in qtys.items():
                rej = max(1, round(q * r.uniform(0.05, 0.2))) if r.random() < defect * 3 else 0
                rej = min(rej, q)
                reason = weighted(r, [("DAMAGED", 0.5), ("QUALITY_FAIL", 0.35), ("WRONG_ITEM", 0.15)]) if rej else None
                rows.append((lid, q, q - rej, rej, reason))
                if rej:
                    rejected_total[lid] = rejected_total.get(lid, 0) + rej
            planned.append([day, rows])
        if rejected_total and not short:
            day = planned[-1][0] + timedelta(days=r.randint(5, 12))
            planned.append([day, [(lid, q, q, 0, None) for lid, q in rejected_total.items()]])
        cat = w.cat[w.item[po["_lines"][0]["item_id"]]["category_code"]]
        for day, rows in planned:
            while not is_workday(day):
                day = next_workday(day)
            carrier = "Service acceptance" if cat["is_service"] else weighted(r, [(c, 1) for c in cd.CARRIERS])
            self.schedule(work_time_on(r, day), "delivery", po, rows, carrier)
        if short:
            close_day = planned[-1][0] + timedelta(days=r.randint(21, 35))
            while not is_workday(close_day):
                close_day = next_workday(close_day)
            self.schedule(add_work_hours(work_time_on(r, close_day), 0), "short_close", po)

    def on_delivery(self, po: dict, rows: list, carrier: str) -> None:
        if po["status"] in ("RECEIVED", "CLOSED_SHORT"):
            return
        w = self.w
        po["_n_deliveries"] += 1
        did = delivery_id(po["po_id"], po["_n_deliveries"])
        by_id = {ln["po_line_id"]: ln for ln in po["_lines"]}
        for n, (lid, q, acc, rej, reason) in enumerate(rows, 1):
            ln = by_id[lid]
            acc = min(acc, ln["quantity"] - ln["qty_received"])
            ln["qty_received"] += acc
            ln["line_status"] = ("RECEIVED" if ln["qty_received"] >= ln["quantity"]
                                 else "PARTIALLY_RECEIVED" if ln["qty_received"] else "OPEN")
            self.delivery_lines.append({"delivery_line_id": line_id(did, n), "delivery_id": did, "po_line_id": lid,
                                        "qty_delivered": acc + rej, "qty_accepted": acc, "qty_rejected": rej,
                                        "rejection_reason": reason})
        complete = all(ln["qty_received"] >= ln["quantity"] for ln in po["_lines"])
        pr0 = po["_sts"][0]["pr"]
        receiver = pr0["requester_id"] if w.is_active_employee(pr0["requester_id"], self.now.date()) else \
            w.budget_by_key[(po["department_id"], "OPEX")]["owner_id"]
        late = (self.now.date() - po["promised_date"]).days
        self.deliveries.append({"delivery_id": did, "po_id": po["po_id"], "delivery_seq": po["_n_deliveries"],
                                "carrier": carrier, "delivered_at": self.now, "received_by": receiver,
                                "is_on_time": late <= 0, "days_late": max(0, late), "completes_po": complete})
        new = ("RECEIVED" if complete else "PARTIALLY_RECEIVED"
               if any(ln["qty_received"] for ln in po["_lines"]) else po["status"])
        if new != po["status"]:
            self.ev.add("PURCHASE_ORDER", po["po_id"], po["status"], new, self.now, receiver, did)
            po["status"] = new
            po["closed_at"] = self.now if complete else None
        for st in po["_sts"]:
            mine = [ln for ln in po["_lines"] if ln["pr_id"] == st["pr"]["pr_id"]]
            to = "RECEIVED" if all(ln["qty_received"] >= ln["quantity"] for ln in mine) else "PARTIALLY_RECEIVED"
            if any(ln["qty_received"] for ln in mine) and to != st["status"]:
                self.set_status(st, to, receiver, did)

    def on_short_close(self, po: dict) -> None:
        if po["status"] in ("RECEIVED", "CLOSED_SHORT"):
            return
        open_value = sum((ln["quantity"] - ln["qty_received"]) * ln["unit_price"] for ln in po["_lines"])
        for ln in po["_lines"]:
            if ln["qty_received"] < ln["quantity"]:
                ln["line_status"] = "CLOSED_SHORT"
        self.ev.add("PURCHASE_ORDER", po["po_id"], po["status"], "CLOSED_SHORT", self.now, po["buyer_id"],
                    "Supplier cannot ship the balance; remainder cancelled")
        po["status"], po["closed_at"] = "CLOSED_SHORT", self.now
        self.ledger.decommit(po, money(open_value * po["fx_rate_to_usd"]), self.now)
        for st in po["_sts"]:
            if st["status"] != "RECEIVED":     # requests on a consolidated PO may already be complete
                self.set_status(st, "CLOSED_SHORT", po["buyer_id"], po["po_id"])
