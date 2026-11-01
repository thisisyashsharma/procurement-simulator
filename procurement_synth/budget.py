"""Budgets (sized from forecast demand) and the append-only budget ledger."""
from __future__ import annotations

import math

from .config import FISCAL_YEAR, FY_END, FY_START
from .master import World
from .util import money, rng, weighted

CONTINGENCY_SHARE = 0.03


def build_budgets(w: World, prs: list[dict]) -> None:
    """One OPEX and one CAPEX budget per department plus a corporate contingency pool.

    Allocation = forecast annual demand x a tightness factor.  Tight budgets are what make
    over-budget requests (and budget exceptions) appear naturally in the second half of the year.
    """
    demand = {}
    for pr in prs:
        if pr["_key"].startswith("B"):              # planners forecast from genuine demand only
            key = (pr["department_id"], w.cat[pr["category_code"]]["budget_type"])
            demand[key] = demand.get(key, 0.0) + pr["estimated_total_usd"]
    r = rng(w.seed, "budgets")
    n = 0
    owners = {rq["department_id"]: rq["requester_id"] for rq in w.requesters if rq["role"] == "DIRECTOR"}
    for d in w.departments:
        for btype in ("OPEX", "CAPEX"):
            n += 1
            forecast = demand.get((d["department_id"], btype), 0.0) * 12 / 10
            factor = weighted(r, [(r.uniform(0.45, 0.62), 0.35), (r.uniform(0.85, 1.05), 0.45), (r.uniform(1.1, 1.3), 0.2)])
            amount = max(10_000, math.ceil(forecast * factor / 5_000) * 5_000)
            w.budgets.append(_row(n, d["department_id"], btype, amount, owners[d["department_id"]]))
    total = sum(b["allocated_amount_usd"] for b in w.budgets)
    exec_dept = w.departments[0]["department_id"]
    w.budgets.append(_row(n + 1, exec_dept, "CONTINGENCY", math.ceil(total * CONTINGENCY_SHARE / 5_000) * 5_000, w.cfo))
    w.budget_by_key = {(b["department_id"], b["budget_type"]): b for b in w.budgets}
    w.contingency_id = w.budgets[-1]["budget_id"]
    for pr in prs:
        pr["budget_id"] = w.budget_by_key[(pr["department_id"], w.cat[pr["category_code"]]["budget_type"])]["budget_id"]


def _row(n, dept, btype, amount, owner) -> dict:
    return {"budget_id": f"BUD-{FISCAL_YEAR}-{n:04d}", "department_id": dept, "fiscal_year": FISCAL_YEAR,
            "budget_type": btype, "allocated_amount_usd": float(amount), "owner_id": owner,
            "effective_from": FY_START, "effective_to": FY_END, "status": "OPEN"}


class Ledger:
    """Running balances + posted rows.  available = allocated + transfers - reserved - committed."""

    def __init__(self, w: World):
        self.w = w
        self.alloc = {b["budget_id"]: b["allocated_amount_usd"] for b in w.budgets}
        self.transfers = {b: 0.0 for b in self.alloc}
        self.reserved = {b: 0.0 for b in self.alloc}
        self.committed = {b: 0.0 for b in self.alloc}
        self.own = {}                  # pr_id -> current reservation
        self.rows: list[dict] = []

    def available(self, budget_id: str, exclude_pr: str | None = None) -> float:
        a = (self.alloc[budget_id] + self.transfers[budget_id] - self.reserved[budget_id]
             - self.committed[budget_id])
        return money(a + (self.own.get(exclude_pr, 0.0) if exclude_pr else 0.0))

    def _post(self, budget_id, ts, txn_type, src_type, src_id, alloc=0.0, res=0.0, com=0.0, note=None):
        alloc, res, com = money(alloc), money(res), money(com)
        self.transfers[budget_id] = money(self.transfers[budget_id] + alloc)
        self.reserved[budget_id] = money(self.reserved[budget_id] + res)
        self.committed[budget_id] = money(self.committed[budget_id] + com)
        self.rows.append({"budget_txn_id": f"BTX-{FISCAL_YEAR}-{len(self.rows) + 1:06d}", "budget_id": budget_id,
                          "txn_ts": ts, "txn_type": txn_type, "source_type": src_type, "source_id": src_id,
                          "allocated_delta_usd": alloc, "reserved_delta_usd": res, "committed_delta_usd": com,
                          "note": note})

    def reserve(self, pr: dict, amount: float, ts) -> None:
        self.own[pr["pr_id"]] = money(amount)
        self._post(pr["budget_id"], ts, "RESERVE", "PURCHASE_REQUEST", pr["pr_id"], res=amount,
                   note="Pre-encumbrance at submission (estimate)")

    def adjust(self, pr: dict, new_amount: float, ts) -> None:
        delta = money(new_amount - self.own.get(pr["pr_id"], 0.0))
        if delta:
            self.own[pr["pr_id"]] = money(new_amount)
            self._post(pr["budget_id"], ts, "RESERVE_ADJUST", "PURCHASE_REQUEST", pr["pr_id"], res=delta,
                       note="Reservation re-based to awarded landed cost")

    def release(self, pr: dict, ts, note: str) -> None:
        amount = self.own.pop(pr["pr_id"], 0.0)
        if amount:
            self._post(pr["budget_id"], ts, "RELEASE", "PURCHASE_REQUEST", pr["pr_id"], res=-amount, note=note)

    def commit(self, po: dict, ts) -> None:
        self._post(po["budget_id"], ts, "COMMIT", "PURCHASE_ORDER", po["po_id"], com=po["total_usd"],
                   note="PO encumbrance")

    def decommit(self, po: dict, amount: float, ts) -> None:
        self._post(po["budget_id"], ts, "DECOMMIT", "PURCHASE_ORDER", po["po_id"], com=-amount,
                   note="Undelivered balance released at short close")

    def transfer(self, budget_id: str, amount: float, ts, approval_id: str) -> None:
        self._post(self.w.contingency_id, ts, "TRANSFER_OUT", "APPROVAL", approval_id, alloc=-amount,
                   note=f"Budget exception transfer to {budget_id}")
        self._post(budget_id, ts, "TRANSFER_IN", "APPROVAL", approval_id, alloc=amount,
                   note="Approved budget exception (from contingency)")
