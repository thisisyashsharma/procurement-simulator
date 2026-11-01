# Requirements coverage

Every point of the problem statement, where it is met, and the evidence. Figures are for
`data/full` with seed 20261022 and can be re-checked in `data/full/reports/` and `data/full/csv/`.

Status: ✅ met · ⚠️ met with a stated deviation

## 1. Business workflow and rules

| # | Requirement | Where it is met | Status |
|---|---|---|:-:|
| 1 | Master data first: Requester, Department, Budget, PurchaseRequest, RequestLine | `generator._run`: `build_master` → `build_demand` → `build_budgets` ([pipeline.md](pipeline.md) section 1) | ✅ |
| 2 | Dependent records use valid parent IDs | FKs on every relationship, enforced in `sql/schema.sql` (SQLite load with `PRAGMA foreign_keys=ON`) and 56 `foreign_key` checks | ✅ |
| 3 | Departments and budgets; requests with item, category, quantity, estimate | `department`, `budget`, `purchase_request`, `request_line` | ✅ |
| 3 | Apply approval thresholds | Tiers APR-T1..T4 ([business_rules.md](business_rules.md) section 4); `approval.rule_id`; acceptance checks on tier, chain completeness, authority, no self-approval, sequence | ✅ |
| 3 | RFQs for eligible requests | Rule SRC-1 (estimate >= $10,000) ([business_rules.md](business_rules.md) section 2) | ✅ |
| 3 | At least three quotes for competitive purchases | 96.5% of competitive RFQs have >= 3 quotes. The rest are documented `COMPETITION_WAIVER` cases or RFQs still open or cancelled at the snapshot. | ✅ |
| 3 | Compare total landed cost and delivery time | `quote_evaluation`: `landed_cost_usd`, `expected_delivery_date`, `meets_need_by`, `landed_cost_rank` | ✅ |
| 3 | Award supplier | `rfq_award` with `award_basis` (AWD-1..4) and `award_rationale` | ✅ |
| 3 | PO lines from the approved quote | `po_line.quote_line_id`; acceptance check "PO values equal awarded quote lines" | ✅ |
| 3 | Delivery events | `delivery`, `delivery_line` (`DEL-<PO-id>-nn`) | ✅ |
| 4 | State changes as records; no overwritten history | `status_event` (every transition), `approval` (one row per step), `budget_transaction` (append-only ledger), effective-dated supplier status and risk | ✅ |
| 5 | Outcomes and labels from documented rules | Every decision carries a rule or reason code; anomalies are planned from baseline opportunities, not random flags ([business_rules.md](business_rules.md) section 10) | ✅ |

## 2. Entities and relationships

| Requirement | Where it is met | Status |
|---|---|:-:|
| 11 core entities | All present, plus 16 supporting tables (bridges, history, derived): [data_dictionary.md](data_dictionary.md) | ✅ |
| PK for every entity, FK for every relationship | Data dictionary "Tables" and "Relationships" sections; 27 `primary_key` + 56 `foreign_key` checks | ✅ |
| Cardinality (1:1, 1:N, N:M), optional relationships | Data dictionary relationship table (cardinality and mandatory/optional columns); [erd.md](erd.md) diagram | ✅ |
| Effective dates | [erd.md](erd.md) "Effective-dated records" | ✅ |
| Lifecycle states | [erd.md](erd.md) state machines for request, RFQ, quote and PO | ✅ |
| Bridge tables for N:M | `supplier_category`, `rfq_supplier`, `po_line` | ✅ |
| Validate all joins | FK checks, polymorphic references resolved by `validate.py`, SQLite load with FKs enforced | ✅ |
| Anomalies labelled, not silent corruption | `ground_truth/` only; the validator checks that the input tables have no label-like columns | ✅ |

## 3. ID conventions

| Brief | Generated example | Status |
|---|---|:-:|
| `PR-2026-000001` | `PR-2026-000588` | ✅ |
| `RFQ-2026-000001` | `RFQ-2026-000240` | ✅ |
| `QUO-<supplier-code>-2026-000001` | `QUO-SUP0107-2026-000763` | ✅ |
| `PO-2026-000001` | `PO-2026-000503` | ✅ |
| `DEL-<PO-id>-01` | `DEL-PO-2026-000503-01` | ✅ |

Zero-padded counters, assigned in event-time order and never changed. 73 `id_format` checks
validate every ID column against its pattern.

## 4. Generation steps 1-10

| Step | Requirement | Evidence | Status |
|---|---|---|:-:|
| 1 | Data dictionary with type, required, allowed values, units, uniqueness, validation rule | [data_dictionary.md](data_dictionary.md), generated from `schema.py` | ✅ |
| 2 | Parents first, then children and events; domain logic | [pipeline.md](pipeline.md) "Order of creation" | ✅ |
| 3 | Deterministic, immutable, consistent IDs | Section 3 above | ✅ |
| 4 | Volumes, coverage scenarios, fixed seed, parameterized scale | Section 5 below; `--scale starter|full`, seed 20261022 | ⚠️ PO count 918 vs 900 |
| 5 | Valid baseline first, then labelled edge cases | Baseline run + injected run ([pipeline.md](pipeline.md) section 2); `reports/baseline_check.json`: 0 findings on the clean run | ✅ |
| 6 | Derived values from source records | Columns marked `derived` in the data dictionary; 12 `arithmetic` + 6 `budget` checks recompute them | ✅ |
| 7 | Separate `ground_truth.csv/json`, no leakage | `data/<scale>/ground_truth/`; 3 `ground_truth` checks | ✅ |
| 8 | Validation: PK, FK, enums, date order, arithmetic, lifecycle, duplicates | Section 7 below | ✅ |
| 9 | CSV/JSON/SQL + README, dictionary, command, seed, manifest, validation summary | `data/<scale>/{csv,json,sql}`, README, `manifest.json` (seed, command, rules, params, row counts, SHA-256, provenance), `reports/validation_summary.md` | ✅ |
| 10 | Regenerate twice, compare counts and checksums | `reports/reproducibility.md`: 58 files identical across the two runs and to the shipped copy; Python version and platform recorded | ✅ |

## 5. Volume and coverage

| Entity | Brief | Generated |
|---|---:|---:|
| Requesters | 300 | 300 |
| Suppliers | 120 | 120 |
| Purchase requests | 1,200 | 1,200 |
| RFQs | 500 | 500 |
| Quotes | 1,500 | 1,500 |
| Purchase orders | 900 | **918** |

The PO count is a rule outcome (rejections, cancellations, open work at the snapshot and weekly
consolidation of direct buys), not a quota. It lands within 5% of the target (899-918 across the
seeds tested).

| Scenario | Count in `data/full` |
|---|---|
| Single-source exceptions | 39 single-source RFQs, each with a Procurement Director approval |
| Over-budget requests | 53 (`budget_check_result = OVER_BUDGET`); 47 budget-exception approvals routed: 21 approved, 25 rejected, 1 pending |
| Split purchases | 5 labelled groups |
| Quote expiry | 52 quotes excluded as `EXPIRED` at evaluation (legitimate), plus 8 labelled expired awards |
| Supplier risk flags | 41 effective-dated flags (18 LOW, 18 MEDIUM, 5 HIGH) |
| Partial deliveries | 161 POs received in 2-4 shipments; 28 short-closed |

## 6. Required negative scenarios

| Issue type | Labels | Detected by `controls.py` |
|---|---:|---:|
| `PO_WITHOUT_APPROVAL` | 10 | 10 |
| `QUOTE_EXPIRED_AT_AWARD` | 8 | 8 |
| `NON_LOWEST_AWARD_NO_RATIONALE` | 10 | 10 |
| `INACTIVE_SUPPLIER` | 6 | 6 |
| `BUDGET_OVERRUN` | 6 | 6 |
| `DUPLICATE_REQUEST` | 14 | 14 |
| `QUOTE_CURRENCY_MISMATCH` | 6 | 6 |
| `SPLIT_PURCHASE` (extra, from the coverage list) | 5 | 5 |

Each label carries its control rule, expected handling and JSON evidence. How each case is
injected and detected is in [business_rules.md](business_rules.md) section 10.

## 7. Validation (step 8) and acceptance criteria

`reports/validation_summary.md`: **547 checks, 0 failing**.

| Brief asks for | Check category | Checks |
|---|---|---:|
| Primary-key uniqueness | `primary_key` | 27 |
| Foreign-key integrity | `foreign_key` | 56 |
| Allowed enums | `enum` | 61 |
| Date ordering | `date_order` | 12 |
| Arithmetic reconciliation | `arithmetic`, `budget` | 12 + 6 |
| Lifecycle transitions | `lifecycle` (+ transition whitelist in `controls`) | 3 |
| Duplicate checks | `uniqueness` (unique and natural keys) + `DUPLICATE_REQUEST` control | 42 |
| Also checked | `required` 221, `id_format` 73, `acceptance` 14, `control` 9, `volume` 6, `ground_truth` 3, `export` 1, `sql` 1 | |

| Acceptance criterion | How it is verified |
|---|---|
| Approval thresholds enforced | Tier = band of the approval basis; completed chains cover every required level; approvers hold the authority and never approve their own requests; steps are sequential |
| Supplier selection is explainable | `quote_evaluation` recomputes landed cost, eligibility and rank; non-lowest awards carry a basis and rationale; the only unexplained ones are the labelled cases. Worked example: [pipeline.md](pipeline.md) section 4.3 |
| PO values equal awarded quote lines | Every RFQ PO line matches its quote line (quantity, unit price, request line), plus freight. Worked example: [pipeline.md](pipeline.md) section 4.5 |
| Budget reservation is consistent | Balances = sum of the ledger; reservation held only while the request is open; re-based at award; commitment = PO value less short-close release; transfers net to zero. Worked example: [pipeline.md](pipeline.md) section 4.7 |
| Every exception has a reason and audit trail | Reason codes on decisions, cancellations, disqualifications and awards; `exception_register` links each exception to its request and authorising approval; `status_event` chains are continuous |

## 8. Evaluation focus

### (a) Realistic distributions and meaningful variation

Demand is shaped by seasonality, department and role weights, category affinity and value bands.
Supplier behaviour comes from hidden per-supplier parameters. Observed mixes in `data/full`:

| Dimension | Distribution |
|---|---|
| Sourcing route | DIRECT 58.3%, COMPETITIVE_RFQ 38.4%, SINGLE_SOURCE_RFQ 3.2% |
| Approval tier | T1 42.9%, T2 29.5%, T3 21.7%, T4 2.2% (3.8% never reached approval) |
| Priority | MEDIUM 54.2%, HIGH 26.8%, LOW 13.1%, CRITICAL 5.8% |
| Request value (USD) | p10 1,165 · p25 2,477 · median 6,782 · p75 29,941 · p90 65,812 · p99 155,496 · max 253,420 |
| Lines per request | 1: 48.6%, 2: 32.8%, 3: 8.9%, 4: 6.7%, 5: 3.1% |
| Monthly requests | Jan 87, Feb 134, **Mar 165**, Apr 137, May 116, **Jun 128**, Jul 98, Aug 82, **Sep 132**, Oct 121 (quarter-end peaks, summer dip; Oct ends at the snapshot) |
| Category | 14 categories; IT_HW and SW_LIC about 13% each, down to FURN at 2.2% |
| Quote currency | USD 85.3%, EUR 4.5%, INR 4.5%, MXN 2.8%, GBP 1.5%, CAD 1.5% |
| Quote incoterm | DAP 46.5%, DDP 34.3%, FCA 11.9%, FOB 5.9%, EXW 1.3% |
| Suppliers | US 80%, 6 other countries; tiers APPROVED 57.5%, PREFERRED 30.8%, STRATEGIC 11.7%; 11 inactive at the snapshot |
| Quotes per RFQ | 3: 70.6%, 4: 15.8%, 5-6: 2.6%, 2: 1.8%, 1 (single source): 8.2%, 0 (open): 1.0% |
| Award basis | LOWEST_LANDED_COST 87.9%, SOLE_SOURCE 7.9%, RISK_MITIGATION 1.3%, DELIVERY_REQUIREMENT 0.7%, none (labelled anomalies) 2.2% |
| Approval cycle (median hours) | T1 6.3, T2 44.6, T3 115.5, T4 174.8 |
| Delivery | 75.0% first deliveries on time; 81.7% of POs in one shipment; 112 inspection rejections (DAMAGED 57, QUALITY_FAIL 35, WRONG_ITEM 20) |

More KPIs are in `reports/metrics.md` (conversion 84.8%, savings vs estimate 12.1%, OTIF 58.7%).

### (b) Consistent IDs and valid joins
Section 3 and section 7 (`id_format`, `primary_key`, `foreign_key`, SQLite load with FKs on).
Polymorphic references (`budget_transaction.source_id`, `status_event.entity_id`,
`exception_register.entity_id`) are resolved by the validator.

### (c) Dependency and lifecycle consistency
Events are simulated in time order up to the snapshot, so no child predates its parent
(12 `date_order` checks). Each entity's `status` equals its last `status_event`, chains are
continuous, and only whitelisted transitions occur. The single exception is the labelled
`PO_WITHOUT_APPROVAL` cases ([erd.md](erd.md)).

### (d) Correct derived values and reconciliation
Totals, landed cost, ranks, statuses, delivery flags and budget balances are derived, never
sampled, and recomputed by 12 `arithmetic` + 6 `budget` + 14 `acceptance` checks.

### (e) Normal, boundary, failure and exception coverage

| Kind | Examples in `data/full` |
|---|---|
| Normal | 939 requests fully received |
| Boundary | Approval basis within 3% of a tier edge: 10 just below / 7 at or just above $5,000, 10 / 6 around $25,000, 5 / 1 around $100,000. 7 competition waivers (fewer than 3 bids). 85 requests still in progress at the snapshot (sourcing, pending approval, approved, ordered or partially received). |
| Failure | 115 rejected requests (insufficient justification, deferred priority, budget exceeded); 32 cancelled; 7 RFQs cancelled with no eligible quote; 59 awards rejected; 63 disqualified quotes |
| Exception (legitimate, documented) | `exception_register`: budget exceptions 47, single source 39, competition waivers 7, non-lowest awards 9, expired quotes 52, disqualified suppliers 11, late deliveries 416, partial deliveries 233, quality rejections 112, short closes 28 |
| Anomaly (labelled) | 65 ground-truth labels across 8 types (section 6) |

The rule that withdraws an award when the awarded supplier is deactivated before the PO
(`AWARDED_SUPPLIER_INACTIVE`) is implemented, but no case occurs with seed 20261022.

### (f) Separate ground truth
Labels exist only in `ground_truth/`. The input tables have no flag columns (checked by the
validator). `controls.detect` finds every label from the input tables alone and finds nothing on
the clean baseline. The 100% precision and recall shows the labels and data agree; it is not a
benchmark of a learned detector.

### (g) Reproducibility, documentation and lawful provenance
- **Reproducibility**: fixed seed 20261022; per-entity random streams; byte-identical output across two runs, and identical to the shipped files by both the manifest checksums and the bytes on disk (`reports/reproducibility.md`, 58 files, with the Python version and platform of the run).
- **Documentation**: README, [HOW_TO_RUN.md](HOW_TO_RUN.md), [pipeline.md](pipeline.md), [business_rules.md](business_rules.md), [erd.md](erd.md), [data_dictionary.md](data_dictionary.md), `manifest.json`.
- **Provenance**: fully synthetic, no external data. Names are random combinations of generic words, e-mail addresses use `example.com`, and FX rates are a synthetic random walk. Recorded in the `provenance` block of `manifest.json`, which lists each external-source field from the brief (source URL, dataset version, retrieval date, licence/terms, attribution, transformations, fields discarded) as not applicable; MIT licence.

## 9. Primary actors

| Actor (brief) | In the data | What they do | Outputs that serve them |
|---|---|---|---|
| Business requester | `requester` with role STAFF, MANAGER, DIRECTOR, BUYER, FINANCE_CONTROLLER or VP (CEO and CFO don't raise requests) | Raise requests, receive deliveries (`delivery.received_by`) | `purchase_request`, `request_line`, `status_event` |
| Process owner | BUYER (8) and the Procurement Director (the DIRECTOR of the Procurement department) | Issue RFQs, evaluate quotes, recommend awards, issue POs; approve single-source and waiver steps | `rfq`, `quote_evaluation`, `rfq_award`, `purchase_order`, `exception_register` |
| Approver | MANAGER, DIRECTOR, VP, CFO, FINANCE_CONTROLLER, Procurement Director | Decide approval steps under APR-T1..T4, BUD-EXC, SRC-SS, SRC-WAIVER | `approval` (rule, decision, reason) |
| Operations analyst | Consumer of the outputs | Monitor KPIs, investigate exceptions, test detection against labels | `reports/metrics.md`, `reports/control_findings.csv`, `exception_register`, `ground_truth/` |
| System administrator | Runs the generator | Generate, validate, reproduce; manage seed and scale | CLI (`python -m procurement_synth`), `manifest.json`, `reports/validation_summary.md`, `reports/reproducibility.md` |

## 10. Stated deviations and limits

- **PO volume** is 918, not 900, because it is a rule outcome (section 5).
- **Detection scores** are 100% by construction, since the controls mirror the injection rules (section 8f).
- **Scope**: single legal entity, USD base currency, no invoices or payments, no public holidays. See README "Assumptions and limitations".
