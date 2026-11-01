# Business rules and generation logic

Every outcome in the dataset comes from the rules below. Rule IDs appear in the data itself
(`approval.rule_id`, `rfq_award.award_basis`, `exception_register.reason_code`), so you can trace
any decision back to this page. The thresholds live in `procurement_synth/config.py`.

## 1. Time frame

| Item | Value |
|---|---|
| Fiscal year | FY2026 (1 Jan to 31 Dec 2026) |
| First request | First business day from 5 Jan 2026 |
| Snapshot (`AS_OF`) | 30 Oct 2026 18:00. Nothing after this has happened yet, so records that are still in progress stay open: pending approvals, open RFQs, undelivered quantities. |
| Working time | Mon-Fri, 08:00-18:00. Approval latencies and buyer lead times are in working hours. Public holidays are ignored. |
| Seasonality | Monthly demand weights (quarter-end peaks in Mar/Jun/Sep, summer dip) and weekday weights (Fri lighter). |

## 2. Sourcing route (SRC-1)

Each request gets its route from its estimate, its items and its need-by date:

| Condition (checked in order) | Route |
|---|---|
| `estimated_total_usd < 10,000` | `DIRECT`: contract (preferred) supplier at contract price, no RFQ |
| any line is an OEM-only item (`item.is_sole_source`) | `SINGLE_SOURCE_RFQ`, reason `SOLE_SOURCE_OEM` |
| priority `CRITICAL` and need-by within 10 days | `SINGLE_SOURCE_RFQ`, reason `EMERGENCY` |
| otherwise | `COMPETITIVE_RFQ`: at least 3 quotes |

The demand mix is stratified so that exactly `scale.rfqs` requests (500 at full scale) fall in the
RFQ band. RFQ creation itself is still the rule above.

## 3. Budget check and reservation

* Budgets are per department x budget type (OPEX/CAPEX, taken from the category), plus one corporate
  `CONTINGENCY` pool. Each allocation = forecast annual demand x a tightness factor (35% of budgets
  are tight at 0.45-0.62, so over-budget requests appear naturally in the second half of the year).
* The ledger (`budget_transaction`) is append-only:

| Event | Posting |
|---|---|
| Request submitted | `RESERVE` +estimate |
| RFQ award recommended | `RESERVE_ADJUST` to the awarded landed cost |
| Budget exception approved | `TRANSFER_OUT` from contingency, `TRANSFER_IN` to the department budget |
| Rejected / cancelled | `RELEASE` the remaining reservation |
| PO issued | `RELEASE` reservation, `COMMIT` `po.total_usd` |
| PO short-closed | `DECOMMIT` the undelivered value |

* **Budget check (BUD-1)** runs when the approval chain starts (at submission for direct buys, at
  award for RFQs): `available = allocated + transfers - reserved - committed`, excluding the
  request's own reservation. If `approval_basis_usd > available`, the request is `OVER_BUDGET`.
* **Budget exception (BUD-EXC)**: an over-budget request first needs a `FINANCE_CONTROLLER` approval.
  Finance approves when cumulative transfers into that budget, including this one, stay within
  15% of the original allocation for HIGH/CRITICAL priority or 5% for MEDIUM, and the contingency
  pool can fund the transfer. LOW priority is always rejected (`BUDGET_EXCEEDED`; `CONTINGENCY_EXHAUSTED`
  when the pool is empty).

## 4. Approval thresholds (APR-T1..T4)

The approval basis is the estimate for direct buys and the awarded landed cost for RFQs
(quote-before-approve: approvers see the actual comparison).

| Tier | Basis (USD) | Levels required (in order) |
|---|---|---|
| 1 (`APR-T1`) | < 5,000 | Manager |
| 2 (`APR-T2`) | 5,000 - 24,999 | Manager, Director |
| 3 (`APR-T3`) | 25,000 - 99,999 | Manager, Director, VP |
| 4 (`APR-T4`) | >= 100,000 | Manager, Director, VP, CFO |

* Approvers are resolved by walking the requester's management chain to the first person whose role
  rank is at least the level (CFO is resolved globally). If one person covers several levels they
  approve once. Requesters never approve their own requests, and the CEO and CFO do not raise requests.
* Steps run sequentially: step n+1 is routed when step n is approved. Chain order: budget exception,
  then single-source or competition waiver (RFQs only), then the spend levels.
* Decision rules (documented reason codes):
  * `R-JUST`: the first spend approver rejects a request with no justification (`INSUFFICIENT_JUSTIFICATION`).
  * `R-VP`: the VP defers LOW-priority spend at tier 3+ (`LOW_PRIORITY_DEFERRED`).
  * `R-CFO`: the CFO defers MEDIUM-priority spend >= 250,000 (`CFO_DEFERRED`).
  * Single-source and competition-waiver steps are approved by the Procurement Director (`JUSTIFICATION_ACCEPTED`).
  * Otherwise `APPROVED` / `WITHIN_POLICY`.
* Latency is log-normal per level (median: manager 5h, director 9h, VP 14h, CFO 20h, controller 8h,
  procurement director 6h, all in working hours).
* Requester withdrawal is an external input event: about 5% of direct buys and 3.5% of RFQs. A
  withdrawal only takes effect if it arrives before the PO is issued, and any pending step becomes `WITHDRAWN`.

## 5. RFQ, quotes and evaluation

* A buyer issues the RFQ 2-24 working hours after submission, with a bid window of 7-14 days.
* **Invitations**: competitive RFQs go to 4-6 suppliers that serve the category, are `ACTIVE` and
  have no open HIGH risk flag on the issue date. Better tiers and more responsive suppliers are
  favoured. Single-source RFQs go to the OEM supplier (or, for emergencies, the active contract supplier).
* **Responses**: suppliers respond according to their latent responsiveness. The number of bids per
  RFQ is allocated so that total quotes equal `scale.quotes` (1,500): 3 for a normal competitive
  RFQ, more for larger RFQs, 2 for the 3% that attract insufficient bids, 1 for single source.
  Bids after the snapshot or after a withdrawal do not exist.
* **Quote content**: unit price = list price x supplier price factor x noise x volume discount
  (x1.08 for foreign DDP). Foreign suppliers quote in their own currency 60% of the time. Validity
  is 14/30/45/60 days. Freight is 1.5-4% of goods for domestic suppliers, 4-9% for foreign ones,
  and 0 for DDP or services.
* **Evaluation (`quote_evaluation`)**, at `rfq.evaluated_at`. 10% of evaluations slip 10-30 days,
  which is what makes quotes expire.
  * `fx_rate_used` = the `fx_rate` for the quote currency in the month the quote was submitted.
  * `landed_cost_usd = goods_usd + freight_usd + duty_usd`, where duty = goods_usd x category
    duty rate when the supplier is non-US and the incoterm is not DDP.
  * `expected_delivery_date` = evaluation date + 2 business days + lead time; `meets_need_by` compares it to the request.
  * Eligible = still valid, supplier `ACTIVE` and supplier risk not `HIGH`; otherwise the quote is
    `DISQUALIFIED` with reason `EXPIRED`, `SUPPLIER_INACTIVE` or `SUPPLIER_HIGH_RISK`.

## 6. Award rules (AWD-1..4)

| Rule | Condition | `award_basis` | Rationale required |
|---|---|---|---|
| AWD-1 | Single source | `SOLE_SOURCE` | yes (auto text) |
| AWD-2 | Lowest eligible landed cost meets need-by | `LOWEST_LANDED_COST` | no |
| AWD-3 | Lowest has an open MEDIUM risk flag and a lower-risk on-time quote is within +3% | `RISK_MITIGATION` | yes |
| AWD-4 | Lowest misses need-by; cheapest on-time quote within +15% | `DELIVERY_REQUIREMENT` | yes |
| - | Nothing meets need-by | `LOWEST_LANDED_COST` | no |
| - | No eligible quote | RFQ `CANCELLED` / `NO_ELIGIBLE_QUOTES` | - |

The award (`rfq_award`) then goes through the approval chain in section 4. If the awarded supplier
is deactivated before the PO can be issued, the award is withdrawn (`AWARDED_SUPPLIER_INACTIVE`).

## 7. Purchase orders

* **RFQ POs**: one per approved award, issued 1-16 working hours after approval. Lines copy the
  awarded quote lines exactly (quantity, unit price, currency, freight, incoterm, lead time).
* **Direct POs**: CRITICAL requests get a PO within 1-8 working hours. Other approved direct buys
  wait for the weekly buyer run (Wednesday 15:00), which consolidates them per contract supplier and
  budget into one PO. That is why PR:PO is N:M through `po_line`. Supplier = rank-1 contract
  supplier if usable, else rank-2, else any usable domestic vendor. Price = list price x (1 -
  contract discount for that category).
* `total_usd = total_amount x fx_rate_to_usd (issue month) + est_duty_usd`. This is the budget commitment.

## 8. Delivery

* Delivery behaviour comes from latent supplier parameters: on-time probability 0.80-0.98 (-0.20
  with an open `DELIVERY_PERFORMANCE` flag), partial-shipment rate 5-25%, and defect rate 0-4%
  (+5% with an open `QUALITY_ISSUE` flag).
* Partial deliveries arrive as 2-3 shipments 3-15 days apart. A quarter of partial POs never get
  the last shipment and are short-closed 21-35 days later (`DECOMMIT` of the open value).
* Rejected units (`DAMAGED`, `QUALITY_FAIL`, `WRONG_ITEM`) are replaced in a later shipment.
* `delivery_id = DEL-<po_id>-nn`, numbered per PO in arrival order. `is_on_time`, `days_late` and
  `completes_po` are derived from the PO promised date and cumulative receipts.

## 9. Documented business exceptions (`exception_register`)

These exceptions are legitimate. Each row carries a reason code, a narrative and, when an approval
is required, the approval that authorised it: `BUDGET_EXCEPTION`, `SINGLE_SOURCE`,
`COMPETITION_WAIVER`, `NON_LOWEST_AWARD` (AWD-3/4), `QUOTE_EXPIRED` and `SUPPLIER_DISQUALIFIED`
(excluded at evaluation), `LATE_DELIVERY`, `PARTIAL_DELIVERY`, `QUALITY_REJECTION`, `SHORT_CLOSE`.

## 10. Injected anomalies (ground truth)

Generation runs twice from the same per-entity random streams:

1. **Baseline**: no injection. The control checks must find nothing (`reports/baseline_check.json`).
2. **Injected**: the baseline counts where each anomaly *could* occur. The plan picks evenly spaced
   opportunities (so cases spread over the year) and the second run applies them. Every applied
   case is written to `ground_truth/` with its control rule, the expected handling and JSON evidence.
   Nothing in the input tables is flagged.

| Issue type | Where it is injected | How | Detection rule (controls.py) |
|---|---|---|---|
| `PO_WITHOUT_APPROVAL` | approval chain start | the buyer releases the PO while step 1 is still pending; the chain then continues | an approval for the request is not `APPROVED` or is decided after `po.issued_at`; also the lifecycle transition `PENDING_APPROVAL -> ORDERED` |
| `QUOTE_EXPIRED_AT_AWARD` | award | the lowest quote's validity lapses before a delayed evaluation, but it is still awarded | `quote.valid_until < award date` |
| `NON_LOWEST_AWARD_NO_RATIONALE` | award | a rank-2/3 eligible quote (<= +30%) is awarded with no basis or rationale | awarded quote is eligible, rank > 1, no rationale |
| `INACTIVE_SUPPLIER` | direct PO | the PO goes to the stale rank-1 contract supplier after its deactivation | supplier status on the PO date is not `ACTIVE` |
| `BUDGET_OVERRUN` | budget check | the over-budget request is not routed to Finance; the chain continues | `budget_check_result = OVER_BUDGET` with no `BUDGET_EXCEPTION` step |
| `DUPLICATE_REQUEST` | demand | the requester re-submits an identical direct buy 3-45 working hours later (35% with reworded justification) | same requester, category, items and quantities within 10 days |
| `QUOTE_CURRENCY_MISMATCH` | RFQ PO | a EUR/GBP/CAD/MXN quote is keyed into a USD PO with the same numbers | PO currency differs from the awarded quote currency |
| `SPLIT_PURCHASE` | demand | one need is split into 2-3 requests, each under the $5,000 tier, within days | same requester and category, shared item, different quantities, each < 5,000, combined >= 5,000 within 7 days |

The knock-on effects are real. For example, a bypassed budget exception leaves less budget, so
later requests in that department are more likely to go over budget, and those are then handled
by the normal rules.
