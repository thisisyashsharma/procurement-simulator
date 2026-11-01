"""Discrete-event simulation of the request -> approval -> PO -> delivery lifecycle.

Events are processed strictly in time order up to the snapshot (AS_OF), so every budget check
sees exactly the ledger state at that instant.  Anything scheduled after AS_OF simply has not
happened yet (pending approvals, open POs, undelivered quantities).
"""
from __future__ import annotations

import heapq
from datetime import timedelta

from .budget import Ledger
from .config import (AS_OF, BUDGET_EXCEPTION_CAP, CFO_DEFER_THRESHOLD_USD, PO_CONSOLIDATION_WEEKDAYS,
                     ROLE_RANK, TIER_LEVELS, TIER_RULE_IDS, tier_for)
from .orders import OrdersMixin
from .util import add_work_hours, at, lognormal_between, money, rng, seq_id

LEVEL_RANK = {"MANAGER": 2, "DIRECTOR": 3, "VP": 4, "CFO": 5}
LATENCY_H = {"MANAGER": 5, "DIRECTOR": 9, "VP": 14, "CFO": 20, "FINANCE_CONTROLLER": 8,
             "PROCUREMENT_DIRECTOR": 6}


class Engine(OrdersMixin):
    def __init__(self, w, prs, rfqs, plan, gt, events):
        self.w, self.plan, self.gt, self.ev = w, plan, gt, events
        self.ledger = Ledger(w)
        self.queue, self.seq = [], 0
        self.approvals, self.pos, self.po_lines, self.deliveries, self.delivery_lines = [], [], [], [], []
        self.pool = []                          # approved direct buys waiting for the PO run
        self.st = {}
        rfq_by_pr = {q["pr_id"]: q for q in rfqs}
        for pr in prs:
            st = {"pr": pr, "status": None, "rfq": rfq_by_pr.get(pr["pr_id"]), "chain": [], "step": 0,
                  "cancelled": False, "po": None, "early_po": False, "first_spend_done": False}
            self.st[pr["pr_id"]] = st
            for k in ("budget_checked_at", "budget_available_usd", "budget_check_result",
                      "approval_basis_usd", "approval_tier"):
                pr[k] = None
            self.schedule(pr["submitted_at"], "submit", st)
        day = prs[0]["submitted_at"].date()
        while day <= AS_OF.date():
            if day.weekday() in PO_CONSOLIDATION_WEEKDAYS:
                self.schedule(at(day, 15), "po_run")
            day += timedelta(days=1)

    # ---------------------------------------------------------------- loop
    def schedule(self, ts, kind, *payload) -> None:
        self.seq += 1
        heapq.heappush(self.queue, (ts, self.seq, kind, payload))

    def run(self) -> "Engine":
        while self.queue and self.queue[0][0] <= AS_OF:
            ts, _, kind, payload = heapq.heappop(self.queue)
            self.now = ts
            getattr(self, "on_" + kind)(*payload)
        return self

    def set_status(self, st, to, actor=None, reason=None) -> None:
        self.ev.add("PURCHASE_REQUEST", st["pr"]["pr_id"], st["status"], to, self.now, actor, reason)
        st["status"] = to

    # ---------------------------------------------------------------- request intake
    def on_submit(self, st) -> None:
        pr = st["pr"]
        self.set_status(st, "SUBMITTED", pr["requester_id"], pr["sourcing_route"])
        self.ledger.reserve(pr, pr["estimated_total_usd"], self.now)
        rfq = st["rfq"]
        if rfq is None:
            if pr["_cancel_u"] < self.w.cfg.params.cancel_rate_direct:
                self.schedule(add_work_hours(self.now, pr["_cancel_hours"]), "cancel", st, "REQUIREMENT_WITHDRAWN")
            self.start_chain(st, pr["estimated_total_usd"])
            return
        self.schedule(rfq["issued_at"], "rfq_issue", st)
        if rfq["cancel_reason"] == "REQUIREMENT_WITHDRAWN":
            self.schedule(rfq["_cancel_at"], "cancel", st, "REQUIREMENT_WITHDRAWN")
        elif rfq["cancel_reason"] == "NO_ELIGIBLE_QUOTES":
            self.schedule(rfq["evaluated_at"], "cancel", st, "NO_ELIGIBLE_QUOTES")
        elif rfq["_award"]:
            self.schedule(rfq["evaluated_at"], "award", st)

    def on_rfq_issue(self, st) -> None:
        if not st["cancelled"]:
            self.set_status(st, "SOURCING", st["rfq"]["buyer_id"], st["rfq"]["rfq_id"])

    def on_award(self, st) -> None:
        if st["cancelled"]:
            return
        award = st["rfq"]["_award"]
        self.ledger.adjust(st["pr"], award["awarded_landed_cost_usd"], self.now)
        self.start_chain(st, award["awarded_landed_cost_usd"])

    def on_cancel(self, st, reason) -> None:
        if st["cancelled"] or st["po"] or st["status"] not in ("SUBMITTED", "SOURCING", "PENDING_APPROVAL", "APPROVED"):
            return                                  # too late: already ordered / decided
        st["cancelled"] = True
        for rec in self.approvals:
            if rec["_st"] is st and rec["decision"] == "PENDING":
                rec.update(decision="WITHDRAWN", decided_at=self.now, decision_reason="REQUEST_WITHDRAWN",
                           comment="Requester withdrew the request")
        if st in self.pool:
            self.pool.remove(st)
        self.ledger.release(st["pr"], self.now, f"Request cancelled ({reason})")
        actor = st["pr"]["requester_id"] if reason == "REQUIREMENT_WITHDRAWN" else st["rfq"]["buyer_id"]
        self.set_status(st, "CANCELLED", actor, reason)

    # ---------------------------------------------------------------- approvals
    def resolve(self, requester_id: str, level: str) -> str:
        w = self.w
        if level == "CFO":
            return w.cfo if requester_id != w.cfo else w.ceo
        m = w.req[requester_id]["manager_id"]
        while m:
            if ROLE_RANK[w.req[m]["role"]] >= LEVEL_RANK[level]:
                return m
            m = w.req[m]["manager_id"]
        return w.ceo

    def start_chain(self, st, basis: float) -> None:
        w, pr, rfq = self.w, st["pr"], st["rfq"]
        avail = self.ledger.available(pr["budget_id"], exclude_pr=pr["pr_id"])
        over = basis > avail
        tier = tier_for(basis)
        pr.update(budget_checked_at=self.now, budget_available_usd=avail,
                  budget_check_result="OVER_BUDGET" if over else "WITHIN_BUDGET",
                  approval_basis_usd=money(basis), approval_tier=tier)
        steps = []
        if over:
            overrun = money(basis - max(avail, 0.0))
            if self.plan.chance("BUDGET_OVERRUN", pr["pr_id"]):
                self.gt.add("BUDGET_OVERRUN", "EXCEPTION_BYPASSED", "PURCHASE_REQUEST", pr["pr_id"],
                            related=[pr["budget_id"]] + ([rfq["rfq_id"]] if rfq else []),
                            description=f"Budget check failed ({basis:,.2f} USD requested vs {avail:,.2f} available) "
                                        f"but no BUDGET_EXCEPTION approval was routed.",
                            budget_id=pr["budget_id"], basis_usd=money(basis), available_usd=avail,
                            overrun_usd=overrun, checked_at=str(self.now))
            else:
                ctrl = w.controllers[int(rng(w.seed, "ctrl", pr["pr_id"]).random() * len(w.controllers))]
                steps.append(["BUDGET_EXCEPTION", "FINANCE_CONTROLLER", ctrl, "BUD-EXC", overrun])
        if rfq:
            if rfq["sourcing_type"] == "SINGLE_SOURCE":
                steps.append(["SINGLE_SOURCE", "PROCUREMENT_DIRECTOR", w.procurement_director, "SRC-SS", None])
            elif rfq["quotes_received"] < rfq["min_quotes_required"]:
                steps.append(["COMPETITION_WAIVER", "PROCUREMENT_DIRECTOR", w.procurement_director, "SRC-WAIVER", None])
        seen = set()
        for level in TIER_LEVELS[tier]:
            approver = self.resolve(pr["requester_id"], level)
            if approver not in seen:
                seen.add(approver)
                steps.append(["SPEND", level, approver, TIER_RULE_IDS[tier], None])
        st["chain"], st["step"] = steps, 0
        self.set_status(st, "PENDING_APPROVAL", None, f"{len(steps)} approval step(s), tier {tier}")
        first = self.request_step(st)
        if not over and self.plan.chance("PO_WITHOUT_APPROVAL", pr["pr_id"]):
            st["early_po"] = True
            r = rng(w.seed, "early-po", pr["pr_id"])
            t = add_work_hours(self.now, r.uniform(0.3, 2.5))
            if t >= first["_decide_at"]:
                t = self.now + (first["_decide_at"] - self.now) / 2
            self.schedule(t, "early_po", st)

    def request_step(self, st) -> dict:
        typ, level, approver, rule, overrun = st["chain"][st["step"]]
        pr = st["pr"]
        r = rng(self.w.seed, "approval", pr["pr_id"], st["step"], typ)
        hours = lognormal_between(r, LATENCY_H[level], 0.8, 0.25, 120)
        rec = {"approval_id": seq_id("APR", len(self.approvals) + 1), "pr_id": pr["pr_id"],
               "rfq_id": st["rfq"]["rfq_id"] if st["rfq"] else None, "approval_type": typ,
               "approval_level": level, "step_no": st["step"] + 1, "approver_id": approver,
               "basis_amount_usd": overrun if typ == "BUDGET_EXCEPTION" else pr["approval_basis_usd"],
               "rule_id": rule, "requested_at": self.now, "decided_at": None, "decision": "PENDING",
               "decision_reason": None, "comment": None, "_st": st, "_decide_at": add_work_hours(self.now, hours)}
        self.approvals.append(rec)
        self.schedule(rec["_decide_at"], "decide", rec)
        return rec

    def rule_decision(self, rec, st):
        pr, typ = st["pr"], rec["approval_type"]
        if typ == "BUDGET_EXCEPTION":
            b = pr["budget_id"]
            cap = BUDGET_EXCEPTION_CAP[pr["priority"]] * self.ledger.alloc[b]
            if pr["priority"] == "LOW" or self.ledger.transfers[b] + rec["basis_amount_usd"] > cap:
                return "REJECTED", "BUDGET_EXCEEDED", f"Overrun exceeds the {pr['priority']} priority transfer cap"
            if rec["basis_amount_usd"] > self.ledger.available(self.w.contingency_id):
                return "REJECTED", "CONTINGENCY_EXHAUSTED", "Corporate contingency exhausted"
            return "APPROVED", "WITHIN_POLICY", f"Transfer {rec['basis_amount_usd']:,.2f} USD from contingency"
        if typ in ("SINGLE_SOURCE", "COMPETITION_WAIVER"):
            return "APPROVED", "JUSTIFICATION_ACCEPTED", "Exception justification reviewed"
        if not st["first_spend_done"]:
            st["first_spend_done"] = True
            if not pr["justification"]:
                return "REJECTED", "INSUFFICIENT_JUSTIFICATION", "No business justification provided"
        if rec["approval_level"] == "VP" and pr["priority"] == "LOW":
            return "REJECTED", "LOW_PRIORITY_DEFERRED", "Low-priority spend at tier 3+ deferred"
        if rec["approval_level"] == "CFO" and pr["priority"] == "MEDIUM" and rec["basis_amount_usd"] >= CFO_DEFER_THRESHOLD_USD:
            return "REJECTED", "CFO_DEFERRED", "Medium-priority spend above 250k deferred to next cycle"
        return "APPROVED", "WITHIN_POLICY", None

    def on_decide(self, rec) -> None:
        st = rec["_st"]
        if rec["decision"] != "PENDING" or st["cancelled"]:
            return
        decision, reason, comment = self.rule_decision(rec, st)
        rec.update(decided_at=self.now, decision=decision, decision_reason=reason, comment=comment)
        if decision == "APPROVED" and rec["approval_type"] == "BUDGET_EXCEPTION":
            self.ledger.transfer(st["pr"]["budget_id"], rec["basis_amount_usd"], self.now, rec["approval_id"])
        if decision == "REJECTED":
            self.on_rejected(st, rec)
            return
        st["step"] += 1
        if st["step"] < len(st["chain"]):
            self.request_step(st)
        else:
            self.on_chain_approved(st, rec)

    def on_rejected(self, st, rec) -> None:
        if st["status"] == "PENDING_APPROVAL":
            self.set_status(st, "REJECTED", rec["approver_id"], rec["decision_reason"])
        self.ledger.release(st["pr"], self.now, f"Rejected ({rec['decision_reason']})")
        self.close_award(st, "REJECTED", rec["approver_id"])

    def on_chain_approved(self, st, rec) -> None:
        pr = st["pr"]
        if st["status"] == "PENDING_APPROVAL":
            self.set_status(st, "APPROVED", rec["approver_id"], "Approval chain complete")
        self.close_award(st, "APPROVED", rec["approver_id"])
        if st["po"] or st["early_po"]:
            return
        r = rng(self.w.seed, "po-lag", pr["pr_id"])
        if st["rfq"]:
            self.schedule(add_work_hours(self.now, r.uniform(1, 16)), "po_issue", st)
        elif pr["priority"] == "CRITICAL":
            self.schedule(add_work_hours(self.now, r.uniform(1, 8)), "po_issue", st)
        else:
            self.pool.append(st)

    def close_award(self, st, outcome: str, actor: str) -> None:
        rfq = st["rfq"]
        if not rfq or not rfq["_award"] or rfq["_award"]["status"] != "PENDING_APPROVAL":
            return
        award = rfq["_award"]
        award.update(status=outcome, decided_at=self.now)
        to = "AWARDED" if outcome == "APPROVED" else "AWARD_REJECTED"
        self.ev.add("RFQ", rfq["rfq_id"], "AWARD_RECOMMENDED", to, self.now, actor, "Award approval " + outcome.lower())
        self.ev.add("SUPPLIER_QUOTE", award["quote_id"], "SELECTED", to, self.now, actor, None)

    def baseline_counts(self) -> dict:
        return dict(self.plan.counts)
