# Process metrics - starter (seed 20261022)

## Volumes vs brief

| Entity | Target | Actual |
|---|---:|---:|
| requesters | 60 | 60 |
| suppliers | 36 | 36 |
| purchase_request | 120 | 120 |
| rfq | 50 | 50 |
| supplier_quote | 150 | 150 |
| purchase_order | 90 | 101 |

## Key indicators

| Area | Indicator | Value |
|---|---|---:|
| Requests | PR -> PO conversion | 86.7% |
| Requests | Rejected / cancelled | 10.0% / 3.3% |
| Sourcing | Competitive RFQs with >= 3 quotes | 95.6% |
| Sourcing | Avg quotes per competitive RFQ | 3.22 |
| Sourcing | Single-source share of RFQs | 10.0% |
| Sourcing | Awards to lowest eligible landed cost | 91.7% |
| Sourcing | Savings vs requester estimate (approved awards) | 13.7% |
| Sourcing | Quotes expired at evaluation | 5.4% |
| Orders | POs (RFQ award / direct) | 41 / 60 |
| Orders | Consolidated direct POs | 3.0% |
| Delivery | First delivery on time | 66.7% |
| Delivery | OTIF (closed POs) | 44.7% |
| Delivery | POs with partial delivery or short close | 29.7% |
| Delivery | Units rejected at inspection | 0.1% |
| Budget | Over-budget requests | 9 |
| Budget | Budget exception decisions | {'APPROVED': 3, 'REJECTED': 4} |

## Approval cycle time (hours, fully approved chains)

| Tier | n | Median | P90 |
|---|---:|---:|---:|
| 1 | 41 | 8.6 | 29.3 |
| 2 | 44 | 26.4 | 95.5 |
| 3 | 17 | 120.2 | 197.8 |
| 4 | 2 | 306.8 | 306.8 |

## Documented business exceptions

| Type | Count |
|---|---:|
| BUDGET_EXCEPTION | 7 |
| LATE_DELIVERY | 68 |
| PARTIAL_DELIVERY | 43 |
| QUALITY_REJECTION | 20 |
| QUOTE_EXPIRED | 6 |
| SHORT_CLOSE | 5 |
| SINGLE_SOURCE | 5 |
| SUPPLIER_DISQUALIFIED | 1 |

## Control checks vs ground truth

Rule-based checks in `procurement_synth/controls.py` read only the published tables.

| Issue type | Labelled | Detected | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| BUDGET_OVERRUN | 2 | 2 | 1.0 | 1.0 | 1.0 |
| DUPLICATE_REQUEST | 3 | 3 | 1.0 | 1.0 | 1.0 |
| INACTIVE_SUPPLIER | 2 | 2 | 1.0 | 1.0 | 1.0 |
| NON_LOWEST_AWARD_NO_RATIONALE | 2 | 2 | 1.0 | 1.0 | 1.0 |
| PO_WITHOUT_APPROVAL | 2 | 2 | 1.0 | 1.0 | 1.0 |
| QUOTE_CURRENCY_MISMATCH | 1 | 1 | 1.0 | 1.0 | 1.0 |
| QUOTE_EXPIRED_AT_AWARD | 2 | 2 | 1.0 | 1.0 | 1.0 |
| SPLIT_PURCHASE | 2 | 2 | 1.0 | 1.0 | 1.0 |
