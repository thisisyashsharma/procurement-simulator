# Process metrics - full (seed 20261022)

## Volumes vs brief

| Entity | Target | Actual |
|---|---:|---:|
| requesters | 300 | 300 |
| suppliers | 120 | 120 |
| purchase_request | 1200 | 1200 |
| rfq | 500 | 500 |
| supplier_quote | 1500 | 1500 |
| purchase_order | 900 | 918 |

## Key indicators

| Area | Indicator | Value |
|---|---|---:|
| Requests | PR -> PO conversion | 84.8% |
| Requests | Rejected / cancelled | 9.6% / 2.7% |
| Sourcing | Competitive RFQs with >= 3 quotes | 96.5% |
| Sourcing | Avg quotes per competitive RFQ | 3.17 |
| Sourcing | Single-source share of RFQs | 7.8% |
| Sourcing | Awards to lowest eligible landed cost | 94.1% |
| Sourcing | Savings vs requester estimate (approved awards) | 12.1% |
| Sourcing | Quotes expired at evaluation | 4.4% |
| Orders | POs (RFQ award / direct) | 393 / 525 |
| Orders | Consolidated direct POs | 8.9% |
| Delivery | First delivery on time | 75.0% |
| Delivery | OTIF (closed POs) | 58.7% |
| Delivery | POs with partial delivery or short close | 19.9% |
| Delivery | Units rejected at inspection | 0.6% |
| Budget | Over-budget requests | 53 |
| Budget | Budget exception decisions | {'APPROVED': 21, 'PENDING': 1, 'REJECTED': 25} |

## Approval cycle time (hours, fully approved chains)

| Tier | n | Median | P90 |
|---|---:|---:|---:|
| 1 | 472 | 6.3 | 43.7 |
| 2 | 326 | 44.6 | 119.1 |
| 3 | 211 | 115.5 | 211.9 |
| 4 | 21 | 174.8 | 331.7 |

## Documented business exceptions

| Type | Count |
|---|---:|
| BUDGET_EXCEPTION | 47 |
| COMPETITION_WAIVER | 7 |
| LATE_DELIVERY | 416 |
| NON_LOWEST_AWARD | 9 |
| PARTIAL_DELIVERY | 233 |
| QUALITY_REJECTION | 112 |
| QUOTE_EXPIRED | 52 |
| SHORT_CLOSE | 28 |
| SINGLE_SOURCE | 39 |
| SUPPLIER_DISQUALIFIED | 11 |

## Control checks vs ground truth

Rule-based checks in `procurement_synth/controls.py` read only the published tables.

| Issue type | Labelled | Detected | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| BUDGET_OVERRUN | 6 | 6 | 1.0 | 1.0 | 1.0 |
| DUPLICATE_REQUEST | 14 | 14 | 1.0 | 1.0 | 1.0 |
| INACTIVE_SUPPLIER | 6 | 6 | 1.0 | 1.0 | 1.0 |
| NON_LOWEST_AWARD_NO_RATIONALE | 10 | 10 | 1.0 | 1.0 | 1.0 |
| PO_WITHOUT_APPROVAL | 10 | 10 | 1.0 | 1.0 | 1.0 |
| QUOTE_CURRENCY_MISMATCH | 6 | 6 | 1.0 | 1.0 | 1.0 |
| QUOTE_EXPIRED_AT_AWARD | 8 | 8 | 1.0 | 1.0 | 1.0 |
| SPLIT_PURCHASE | 5 | 5 | 1.0 | 1.0 | 1.0 |
