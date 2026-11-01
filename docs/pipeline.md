# Pipeline walkthrough

How the generator turns a seed into a validated dataset, which file does each step, and what one
request looks like in the output. For the rules behind each decision see
[business_rules.md](business_rules.md); for the tables see [erd.md](erd.md) and
[data_dictionary.md](data_dictionary.md); for commands see [HOW_TO_RUN.md](HOW_TO_RUN.md).

## 1. Pipeline at a glance

```
config -> master data -> demand -> budgets -> sourcing -> process simulation -> finalize
       -> export -> validate + controls + metrics -> reproduce
```

`generator.generate()` runs the generation stages (2-8); `cli.py` adds export, checks and reports.
While it runs, the command line prints each stage as it starts, for example
`baseline run: master data > demand > budgets > sourcing > process simulation > finalize`.

| # | Stage | File | Entry point | What it produces |
|---|---|---|---|---|
| 1 | Configuration | `config.py`, `schema.py` | `RunConfig`, `SCALES`, `TABLES` | Seed, scale preset, thresholds, snapshot date; the 27 table definitions |
| 2 | Master data | `master.py` (+ `catalog_data.py`) | `build_master(cfg)` | `World`: departments, org chart, categories, items, suppliers, effective-dated status and risk, FX |
| 3 | Demand | `demand.py` | `build_demand(w, gt)` | Purchase requests and lines; injected duplicates and split purchases |
| 4 | Budgets | `budget.py` | `build_budgets(w, prs)` | OPEX/CAPEX budget per department plus a contingency pool; the ledger class |
| 5 | Sourcing | `sourcing.py` | `plan_sourcing(w, prs, gt, ev)` | RFQs, invitations, quotes, quote evaluations, award recommendations |
| 6 | Process simulation | `engine.py`, `orders.py` | `Engine(...).run()` | Budget checks, approval steps, POs, deliveries, short-closes, status events, ledger postings |
| 7 | Anomaly plan | `anomalies.py` | `AnomalyPlan`, `GroundTruth` | Which cases to inject (used in stages 3, 5, 6) and the ground-truth labels |
| 8 | Finalize | `finalize.py` | `finalize(...)` | Statuses from the last event, budget balances, exception register; latent `_` fields removed |
| 9 | Export | `export.py` | `export(ds, out)` | CSV, JSON, `schema.sql`, `seed.sql`, ground truth, `manifest.json` with SHA-256 |
| 10 | Validate | `validate.py`, `checks_domain.py` | `validate.run(data)` | `reports/validation_summary.md` (547 checks) |
| 11 | Controls | `controls.py` | `detect(T)`, `reconcile(...)` | `reports/control_findings.csv`; findings matched to ground truth |
| 12 | Metrics | `metrics.py` | `metrics.write(...)` | `reports/metrics.md` (process KPIs and detection scores) |
| 13 | Reproduce | `cli.py` | `cmd_reproduce(...)` | `reports/reproducibility.md` (two runs, same checksums) |
| 14 | Docs | `docs.py` | `write_data_dictionary(...)` | `docs/data_dictionary.md` |

Shared helpers live in `util.py`: per-entity random streams, money rounding, working-time
arithmetic, ID formatting and the `EventLog`.

### Order of creation

Only master data exists before the process starts. Transaction records are created by the stage
that owns them, when their parent exists:

* Requests and request lines are created in stage 3. RFQs, quotes and evaluations are planned in
  stage 5, because they depend only on master data.
* Approvals, POs, PO lines, deliveries, ledger postings and status events are created in stage 6,
  in time order, as the simulated clock reaches each event. A PO is only created after its
  approval chain completes (except the labelled `PO_WITHOUT_APPROVAL` cases).
* Derived tables (`budget_balance`, `exception_register`) and final statuses come last, in stage 8.

History is never overwritten. Every state change adds a row to `status_event`, `approval` or
`budget_transaction`.

## 2. Baseline run and injected run

`generate()` runs stages 2-8 twice with the same seed:

1. **Baseline**: anomaly injection is off. It counts the places where each anomaly type *could*
   happen (the opportunities). `controls.detect` on this run must find nothing
   (`reports/baseline_check.json`).
2. **Injected**: `AnomalyPlan.from_baseline` picks evenly spaced opportunities, and the second run
   applies them. Each applied case is written to `ground_truth/`.

Both runs draw from the same per-entity random streams (`util.rng(seed, "entity", key)`). A stream
depends only on the seed and the entity key, not on how many records came before it. So the
injected dataset differs from the baseline only at the labelled cases and their natural knock-on
effects.

## 3. Glossary

| Term | Meaning |
|---|---|
| PR (purchase request) | An employee's request to buy something, with items, quantities and an estimate |
| RFQ (request for quotation) | Invitation to suppliers to bid. Created for requests estimated at $10,000 or more (rule SRC-1) |
| Competitive / single source | Competitive RFQs need at least 3 quotes. Single source means one supplier (OEM-only item or emergency) and needs Procurement Director approval |
| Competition waiver | Approval to award a competitive RFQ with fewer than 3 quotes |
| Landed cost | Total cost in USD to get the goods delivered: goods + freight + import duty, converted at the quote month's FX rate |
| Incoterm (DDP, FCA, ...) | Who pays freight and duty. DDP: supplier delivers duty paid, so no extra freight or duty |
| Approval tier | Spend band (APR-T1..T4) that sets which levels must approve: Manager, Director, VP, CFO |
| Reservation / commitment | Budget is reserved when a request is submitted and committed when the PO is issued. Both are ledger postings |
| Budget exception | Finance approval to fund an over-budget request from the contingency pool |
| Short close | Closing a PO before the full quantity arrives; the undelivered value is released from the budget |
| Effective-dated | A record valid for a date range (supplier status, risk flags). Decisions use the value on their own date |
| Snapshot (`AS_OF`) | 30 Oct 2026 18:00. Events after it have not happened yet, so some records are still open |
| Ground truth | The separate list of injected anomalies with evidence. Never joined into the input tables |
| Latent field | Hidden generator parameter (prefix `_`, such as a supplier's true on-time rate). Drives the simulation, removed on export |

## 4. Follow one request

`PR-2026-000588` in `data/full` (seed 20261022) is a clean competitive purchase: three quotes,
a tier-3 approval chain, one PO and a delivery with a rejection. Every value below is copied from
`data/full/csv`.

### 4.1 Request (`purchase_request`, `request_line`)

* Raised on 2026-05-19 10:47 by `EMP-00124` (staff, IT Infrastructure `DEPT-006`), charged to the
  CAPEX budget `BUD-2026-0012`. Priority MEDIUM, need-by 2026-07-06.
* One line, `PR-2026-000588-L01`: 24 x `ITM-00015` (UPS 3kVA) at an estimated $2,087.05 =
  **$50,089.20**.
* Estimate >= $10,000 and no OEM-only item, so SRC-1 gives `COMPETITIVE_RFQ`.

### 4.2 RFQ and quotes (`rfq`, `rfq_supplier`, `supplier_quote`)

* Buyer `EMP-00074` issued `RFQ-2026-000240` on 2026-05-20 17:38 to 6 suppliers, bids due 05-29.
* 3 quoted, 1 declined and 2 did not respond.

| Quote | Supplier | Currency, incoterm | Total quoted | Lead time |
|---|---|---|---:|---:|
| `QUO-SUP0107-2026-000763` | SUP0107 (US) | USD, DDP | 40,506.96 | 13 days |
| `QUO-SUP0079-2026-000755` | SUP0079 (US) | USD, DDP | 44,271.84 | 12 days |
| `QUO-SUP0093-2026-000720` | SUP0093 (MX) | MXN, FCA | 956,694.00 MXN | 31 days |

### 4.3 Evaluation and award (`quote_evaluation`, `rfq_award`)

Evaluated on 2026-06-02 12:45. All three quotes are valid, from ACTIVE suppliers with no risk flag,
so all are eligible.

| Rank | Quote | Goods USD | Freight USD | Duty USD | Landed cost USD | Meets need-by |
|---:|---|---:|---:|---:|---:|:-:|
| 1 | SUP0107 | 40,506.96 | 0.00 | 0.00 | **40,506.96** | yes |
| 2 | SUP0079 | 44,271.84 | 0.00 | 0.00 | 44,271.84 | yes |
| 3 | SUP0093 | 48,874.66 | 3,685.15 | 977.49 | 53,537.30 | yes |

The MXN quote is converted at 0.054939 USD/MXN. Duty is 2% of goods (IT_HW duty rate), because the
supplier is non-US and the incoterm is not DDP. Rank 1 meets the need-by date, so AWD-2 awards
`LOWEST_LANDED_COST` with no rationale needed.

### 4.4 Budget check and approvals (`purchase_request`, `approval`)

* The budget check runs at award: available $2,292,914.06, so `WITHIN_BUDGET`.
* The approval basis is the awarded landed cost, $40,506.96, which falls in tier 3 (`APR-T3`).
  Three sequential steps, each `APPROVED` / `WITHIN_POLICY`:

| Step | Approval | Level | Approver | Requested | Decided |
|---:|---|---|---|---|---|
| 1 | `APR-2026-001038` | MANAGER | EMP-00036 | 06-02 12:45 | 06-03 13:02 |
| 2 | `APR-2026-001050` | DIRECTOR | EMP-00012 | 06-03 13:02 | 06-03 17:58 |
| 3 | `APR-2026-001054` | VP | EMP-00004 | 06-03 17:58 | 06-04 16:42 |

### 4.5 Purchase order (`purchase_order`, `po_line`)

* `PO-2026-000503` was issued on 2026-06-08 08:16 to SUP0107: USD, DDP, NET45, promised 2026-06-21,
  total **$40,506.96**.
* Line `PO-2026-000503-L01` copies quote line `QUO-SUP0107-2026-000763-L01` exactly: 24 x $1,687.79.
  It links back to `PR-2026-000588-L01`.

### 4.6 Deliveries (`delivery`, `delivery_line`)

| Delivery | Date | Delivered | Accepted | Rejected | Late | Completes PO |
|---|---|---:|---:|---:|---:|:-:|
| `DEL-PO-2026-000503-01` | 06-22 15:00 | 24 | 21 | 3 (`WRONG_ITEM`) | 1 day | no |
| `DEL-PO-2026-000503-02` | 06-30 09:31 | 3 | 3 | 0 | 9 days | yes |

The 3 rejected units were replaced in the second shipment.

### 4.7 Budget ledger (`budget_transaction`)

| Time | Type | Reserved | Committed | Note |
|---|---|---:|---:|---|
| 05-19 10:47 | RESERVE | +50,089.20 | | Estimate at submission |
| 06-02 12:45 | RESERVE_ADJUST | -9,582.24 | | Re-based to the awarded landed cost |
| 06-08 08:16 | RELEASE | -40,506.96 | | Converted to the PO |
| 06-08 08:16 | COMMIT | | +40,506.96 | PO value |

The reservation nets to zero and the commitment equals `po.total_usd`.

### 4.8 History and exceptions (`status_event`, `exception_register`)

```
PR   SUBMITTED -> SOURCING -> PENDING_APPROVAL -> APPROVED -> ORDERED -> PARTIALLY_RECEIVED -> RECEIVED
RFQ  OPEN -> UNDER_EVALUATION -> AWARD_RECOMMENDED -> AWARDED
PO   ISSUED -> PARTIALLY_RECEIVED -> RECEIVED
```

The exception register has 4 legitimate entries for this request: `LATE_DELIVERY` (x2),
`PARTIAL_DELIVERY` and `QUALITY_REJECTION`. Each has a reason and a narrative. The request has no
ground-truth label.

### 4.9 Trace it yourself

Any of these IDs finds every related row:

```bash
grep -h "PR-2026-000588" data/full/csv/*.csv
grep -h "RFQ-2026-000240" data/full/csv/*.csv
grep -h "PO-2026-000503" data/full/csv/*.csv
```
