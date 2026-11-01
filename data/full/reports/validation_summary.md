# Validation summary - full

**Result: PASS** - 547 checks, 0 failing.

| Category | Checks | Failing |
|---|---:|---:|
| primary_key | 27 | 0 |
| required | 221 | 0 |
| id_format | 73 | 0 |
| uniqueness | 42 | 0 |
| enum | 61 | 0 |
| foreign_key | 56 | 0 |
| date_order | 12 | 0 |
| arithmetic | 12 | 0 |
| acceptance | 14 | 0 |
| budget | 6 | 0 |
| lifecycle | 3 | 0 |
| volume | 6 | 0 |
| ground_truth | 3 | 0 |
| export | 1 | 0 |
| sql | 1 | 0 |
| control | 9 | 0 |

## Non-trivial checks

| Category | Check | Checked | Violations | Pass | Note |
|---|---|---:|---:|:-:|---|
| date_order | all event timestamps <= snapshot 2026-10-30 18:00:00 (bid deadlines excepted) | 38457 | 0 | yes |  |
| date_order | requester termination_date >= hire_date | 300 | 0 | yes |  |
| date_order | requester employed on the request submission date | 1200 | 0 | yes |  |
| date_order | need_by_date after submission | 1200 | 0 | yes |  |
| date_order | RFQ issued >= request submitted; due > issued; evaluated >= due | 500 | 0 | yes |  |
| date_order | quote submitted within the RFQ bid window; valid_until >= submission | 1500 | 0 | yes |  |
| date_order | invitation response after invitation | 2354 | 0 | yes |  |
| date_order | approval requested after submission (and after evaluation for awards); decided >= requested | 1978 | 0 | yes |  |
| date_order | PO issued after every request it fulfils (and after RFQ evaluation) | 918 | 0 | yes |  |
| date_order | delivery after PO issue | 1076 | 0 | yes |  |
| date_order | supplier status history is contiguous (half-open intervals) | 120 | 0 | yes |  |
| date_order | risk flag cleared after raised | 41 | 0 | yes |  |
| arithmetic | request_line total = quantity x estimated unit price | 2195 | 0 | yes |  |
| arithmetic | request estimated_total = sum of its lines | 1200 | 0 | yes |  |
| arithmetic | quote_line amount = quantity x unit price | 2665 | 0 | yes |  |
| arithmetic | quote goods = sum of lines; total = goods + freight | 1500 | 0 | yes |  |
| arithmetic | quote_evaluation recomputes (FX of quote month, duty rule, landed cost, eligibility) | 1404 | 0 | yes |  |
| arithmetic | landed_cost_rank is the rank among eligible quotes | 500 | 0 | yes |  |
| arithmetic | po_line amount = quantity x unit price; quantity and item = request line | 1841 | 0 | yes |  |
| arithmetic | PO goods/total/FX/duty/total_usd recompute | 918 | 0 | yes |  |
| acceptance | RFQ PO lines, prices, quantities and freight equal the awarded quote lines | 393 | 0 | yes |  |
| acceptance | direct PO prices = list price x (1 - supplier contract discount) | 525 | 0 | yes |  |
| arithmetic | po_line qty_received = sum of accepted delivery quantities; status consistent | 1841 | 0 | yes |  |
| arithmetic | delivery_line accepted + rejected = delivered; reason iff rejected | 2049 | 0 | yes |  |
| arithmetic | delivery on-time / days late / completes_po / sequence recompute | 1076 | 0 | yes |  |
| arithmetic | PO status consistent with line receipt status | 918 | 0 | yes |  |
| budget | budget_balance = allocation + sum of ledger deltas (available = allocated - reserved - committed) | 33 | 0 | yes |  |
| budget | transfers net to zero (contingency out = department in) | 1 | 0 | yes |  |
| budget | every transfer is backed by an APPROVED budget exception of the same amount | 42 | 0 | yes |  |
| budget | reservation = estimate at submission; held while open, fully released once ordered/rejected/cancelled | 1200 | 0 | yes |  |
| budget | after award the reservation is re-based to the awarded landed cost | 455 | 0 | yes |  |
| budget | PO commitment = total_usd, less the open balance released on short close | 918 | 0 | yes |  |
| lifecycle | every request, RFQ, quote and PO has a creation event | 4118 | 0 | yes |  |
| lifecycle | event chains are continuous and time-ordered (from_status = previous to_status) | 4118 | 0 | yes |  |
| lifecycle | current status (and status_updated_at) = last event | 4118 | 0 | yes |  |
| acceptance | approval tier = threshold band of the approval basis (APR-T1..T4) | 1155 | 0 | yes |  |
| acceptance | approval thresholds enforced: completed chains cover every level the tier requires | 1030 | 0 | yes |  |
| acceptance | approvers hold the required authority and never approve their own request | 1978 | 0 | yes |  |
| acceptance | approval steps are sequential (next step routed when the previous is approved) | 1155 | 0 | yes |  |
| acceptance | budget exception approvals exist only for requests that failed the budget check | 47 | 0 | yes |  |
| acceptance | quotes come from invited suppliers; quotes_received = quotes = QUOTED invitations | 500 | 0 | yes |  |
| acceptance | invited suppliers serve the category and were ACTIVE without HIGH risk at issue | 2354 | 0 | yes |  |
| acceptance | approved competitive awards rest on >= 3 quotes or a waiver; single source has a justification approval | 393 | 0 | yes |  |
| acceptance | every exception has a reason: decisions, cancellations, disqualifications, register rows, awards | 2932 | 0 | yes |  |
| acceptance | request lines belong to the request category and use the item unit of measure | 2195 | 0 | yes |  |
| acceptance | request charged to its department budget of the category budget type | 1200 | 0 | yes |  |
| acceptance | sourcing route follows SRC-1 and an RFQ exists exactly for RFQ routes | 1200 | 0 | yes |  |
| volume | requesters: 300 vs target 300 (exact) | 1 | 0 | yes |  |
| volume | suppliers: 120 vs target 120 (exact) | 1 | 0 | yes |  |
| volume | purchase_request: 1200 vs target 1200 (exact) | 1 | 0 | yes |  |
| volume | rfq: 500 vs target 500 (exact) | 1 | 0 | yes |  |
| volume | supplier_quote: 1500 vs target 1500 (exact) | 1 | 0 | yes |  |
| volume | purchase_order: 918 vs target 900 (rule outcome, tolerance 5%) | 1 | 0 | yes |  |
| ground_truth | no label-like columns in input tables | 260 | 0 | yes |  |
| ground_truth | every label references an existing record | 65 | 0 | yes |  |
| ground_truth | label ids unique | 65 | 0 | yes |  |
| export | JSON files have the same rows and columns as CSV | 27 | 0 | yes |  |
| sql | schema.sql + seed.sql load into SQLite with FK enforcement; counts match CSV | 27 | 0 | yes |  |
| control | BUDGET_OVERRUN: 6 detected / 6 labelled | 6 | 0 | yes | every violation is labelled and every label is detected |
| control | DUPLICATE_REQUEST: 14 detected / 14 labelled | 14 | 0 | yes | every violation is labelled and every label is detected |
| control | INACTIVE_SUPPLIER: 6 detected / 6 labelled | 6 | 0 | yes | every violation is labelled and every label is detected |
| control | NON_LOWEST_AWARD_NO_RATIONALE: 10 detected / 10 labelled | 10 | 0 | yes | every violation is labelled and every label is detected |
| control | PO_WITHOUT_APPROVAL: 10 detected / 10 labelled | 10 | 0 | yes | every violation is labelled and every label is detected |
| control | QUOTE_CURRENCY_MISMATCH: 6 detected / 6 labelled | 6 | 0 | yes | every violation is labelled and every label is detected |
| control | QUOTE_EXPIRED_AT_AWARD: 8 detected / 8 labelled | 8 | 0 | yes | every violation is labelled and every label is detected |
| control | SPLIT_PURCHASE: 5 detected / 5 labelled | 5 | 0 | yes | every violation is labelled and every label is detected |
| control | lifecycle whitelist: 10 illegal transitions, all explained by PO_WITHOUT_APPROVAL | 13479 | 0 | yes |  |

Schema-level checks (PK, FK, required, enum, ID format, uniqueness) are counted in the table above; the full list is in `validation_summary.json`.
