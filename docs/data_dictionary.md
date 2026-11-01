# Data dictionary

Generated from `procurement_synth/schema.py` (`python -m procurement_synth docs`). Types are logical; the SQL seed uses the same names. Money columns are rounded half-up to cents; `derived` columns are recomputed from source records and re-checked by the validator.

## Tables

| Table | Kind | Primary key | Description |
|---|---|---|---|
| [department](#department) | Master data | department_id | Organisational unit that owns budgets and requesters. |
| [requester](#requester) | Master data | requester_id | Employee who can raise requests; approvers, buyers and controllers are requesters with elevated roles. |
| [item_category](#item_category) | Reference data | category_code | Spend category; drives budget type, duty and lead time. |
| [supplier](#supplier) | Master data | supplier_id | Vendor master. Status and risk are effective-dated in child tables; the columns here are the snapshot values. |
| [item](#item) | Reference data | item_id | Catalogue item with a list price used for estimates and contract pricing. |
| [supplier_category](#supplier_category) | Bridge (N:M) | supplier_id, category_code | N:M bridge - which suppliers serve which categories, with contract preference. |
| [supplier_status_history](#supplier_status_history) | Event / history (append-only) | status_history_id | Effective-dated supplier status; half-open interval [effective_from, effective_to). |
| [supplier_risk_flag](#supplier_risk_flag) | Event / history (append-only) | risk_flag_id | Risk signals raised against a supplier (effective-dated). |
| [fx_rate](#fx_rate) | Reference data | currency_code, rate_month | Synthetic monthly FX table (USD per unit of currency). |
| [budget](#budget) | Master data | budget_id | Annual FY2026 budget per department and budget type, plus one corporate contingency pool. |
| [purchase_request](#purchase_request) | Transaction | pr_id | Purchase request (PR) header. |
| [request_line](#request_line) | Transaction | pr_line_id | Request line: item, quantity and the requester estimate. |
| [rfq](#rfq) | Transaction | rfq_id | Request for quotation; exactly one per request in the RFQ routes (1:0..1). |
| [rfq_supplier](#rfq_supplier) | Bridge (N:M) | rfq_id, supplier_id | N:M bridge - suppliers invited to an RFQ and their response. |
| [supplier_quote](#supplier_quote) | Transaction | quote_id | Supplier quote header (one per invited supplier that bid). |
| [quote_line](#quote_line) | Transaction | quote_line_id | Quoted price per request line. |
| [quote_evaluation](#quote_evaluation) | Derived | quote_id | Buyer comparison record per quote: landed cost, delivery and eligibility (1:1 with evaluated quotes). |
| [rfq_award](#rfq_award) | Transaction | rfq_id | Award recommendation (decision record) for an RFQ (1:0..1). |
| [approval](#approval) | Event / history (append-only) | approval_id | One row per approval step requested. Steps are sequential; history is never overwritten. |
| [purchase_order](#purchase_order) | Transaction | po_id | Purchase order header. RFQ POs copy the awarded quote; direct POs use contract pricing. |
| [po_line](#po_line) | Transaction | po_line_id | PO line; also the bridge between POs and request lines (PR:PO is N:M). |
| [delivery](#delivery) | Event / history (append-only) | delivery_id | Goods receipt / service acceptance event. Several per PO for partial deliveries. |
| [delivery_line](#delivery_line) | Event / history (append-only) | delivery_line_id | Quantities delivered, accepted and rejected per PO line. |
| [budget_transaction](#budget_transaction) | Event / history (append-only) | budget_txn_id | Append-only budget ledger; balances are sums of deltas. |
| [budget_balance](#budget_balance) | Derived | budget_id | Snapshot balances recomputed from budget + budget_transaction. |
| [status_event](#status_event) | Event / history (append-only) | event_id | Lifecycle history for requests, RFQs, quotes and POs (append-only). |
| [exception_register](#exception_register) | Derived | exception_id | Documented business exceptions with reason and audit references (not anomaly labels). |

## Relationships and cardinality

Every foreign key below is enforced in `sql/schema.sql` and validated on export. `budget_transaction.source_id`, `status_event.entity_id` and `exception_register.entity_id` are polymorphic references (the target table is given by the type column); the validator resolves them.

| Parent | Child | Key | Cardinality | Child side |
|---|---|---|---|---|
| department | requester | `requester.department_id -> department.department_id` | 1 : N | mandatory |
| requester | requester | `requester.manager_id -> requester.requester_id` | 1 : N | optional |
| item_category | item | `item.category_code -> item_category.category_code` | 1 : N | mandatory |
| supplier | item | `item.sole_source_supplier_id -> supplier.supplier_id` | 1 : N | optional |
| supplier | supplier_category | `supplier_category.supplier_id -> supplier.supplier_id` | 1 : N | mandatory |
| item_category | supplier_category | `supplier_category.category_code -> item_category.category_code` | 1 : N | mandatory |
| supplier | supplier_status_history | `supplier_status_history.supplier_id -> supplier.supplier_id` | 1 : N | mandatory |
| supplier | supplier_risk_flag | `supplier_risk_flag.supplier_id -> supplier.supplier_id` | 1 : N | mandatory |
| department | budget | `budget.department_id -> department.department_id` | 1 : N | mandatory |
| requester | budget | `budget.owner_id -> requester.requester_id` | 1 : N | mandatory |
| requester | purchase_request | `purchase_request.requester_id -> requester.requester_id` | 1 : N | mandatory |
| department | purchase_request | `purchase_request.department_id -> department.department_id` | 1 : N | mandatory |
| budget | purchase_request | `purchase_request.budget_id -> budget.budget_id` | 1 : N | mandatory |
| item_category | purchase_request | `purchase_request.category_code -> item_category.category_code` | 1 : N | mandatory |
| purchase_request | request_line | `request_line.pr_id -> purchase_request.pr_id` | 1 : N | mandatory |
| item | request_line | `request_line.item_id -> item.item_id` | 1 : N | mandatory |
| purchase_request | rfq | `rfq.pr_id -> purchase_request.pr_id` | 1 : 0..1 | mandatory |
| requester | rfq | `rfq.buyer_id -> requester.requester_id` | 1 : N | mandatory |
| rfq | rfq_supplier | `rfq_supplier.rfq_id -> rfq.rfq_id` | 1 : N | mandatory |
| supplier | rfq_supplier | `rfq_supplier.supplier_id -> supplier.supplier_id` | 1 : N | mandatory |
| rfq | supplier_quote | `supplier_quote.rfq_id -> rfq.rfq_id` | 1 : N | mandatory |
| supplier | supplier_quote | `supplier_quote.supplier_id -> supplier.supplier_id` | 1 : N | mandatory |
| supplier_quote | quote_line | `quote_line.quote_id -> supplier_quote.quote_id` | 1 : N | mandatory |
| request_line | quote_line | `quote_line.pr_line_id -> request_line.pr_line_id` | 1 : N | mandatory |
| supplier_quote | quote_evaluation | `quote_evaluation.quote_id -> supplier_quote.quote_id` | 1 : 0..1 | mandatory |
| rfq | quote_evaluation | `quote_evaluation.rfq_id -> rfq.rfq_id` | 1 : N | mandatory |
| rfq | rfq_award | `rfq_award.rfq_id -> rfq.rfq_id` | 1 : 0..1 | mandatory |
| supplier_quote | rfq_award | `rfq_award.quote_id -> supplier_quote.quote_id` | 1 : 0..1 | mandatory |
| supplier | rfq_award | `rfq_award.supplier_id -> supplier.supplier_id` | 1 : N | mandatory |
| requester | rfq_award | `rfq_award.buyer_id -> requester.requester_id` | 1 : N | mandatory |
| purchase_request | approval | `approval.pr_id -> purchase_request.pr_id` | 1 : N | mandatory |
| rfq | approval | `approval.rfq_id -> rfq.rfq_id` | 1 : N | optional |
| requester | approval | `approval.approver_id -> requester.requester_id` | 1 : N | mandatory |
| supplier | purchase_order | `purchase_order.supplier_id -> supplier.supplier_id` | 1 : N | mandatory |
| department | purchase_order | `purchase_order.department_id -> department.department_id` | 1 : N | mandatory |
| budget | purchase_order | `purchase_order.budget_id -> budget.budget_id` | 1 : N | mandatory |
| requester | purchase_order | `purchase_order.buyer_id -> requester.requester_id` | 1 : N | mandatory |
| rfq | purchase_order | `purchase_order.rfq_id -> rfq.rfq_id` | 1 : N | optional |
| supplier_quote | purchase_order | `purchase_order.quote_id -> supplier_quote.quote_id` | 1 : N | optional |
| purchase_order | po_line | `po_line.po_id -> purchase_order.po_id` | 1 : N | mandatory |
| purchase_request | po_line | `po_line.pr_id -> purchase_request.pr_id` | 1 : N | mandatory |
| request_line | po_line | `po_line.pr_line_id -> request_line.pr_line_id` | 1 : 0..1 | mandatory |
| quote_line | po_line | `po_line.quote_line_id -> quote_line.quote_line_id` | 1 : N | optional |
| item | po_line | `po_line.item_id -> item.item_id` | 1 : N | mandatory |
| purchase_order | delivery | `delivery.po_id -> purchase_order.po_id` | 1 : N | mandatory |
| requester | delivery | `delivery.received_by -> requester.requester_id` | 1 : N | mandatory |
| delivery | delivery_line | `delivery_line.delivery_id -> delivery.delivery_id` | 1 : N | mandatory |
| po_line | delivery_line | `delivery_line.po_line_id -> po_line.po_line_id` | 1 : N | mandatory |
| budget | budget_transaction | `budget_transaction.budget_id -> budget.budget_id` | 1 : N | mandatory |
| budget | budget_balance | `budget_balance.budget_id -> budget.budget_id` | 1 : 0..1 | mandatory |
| requester | status_event | `status_event.actor_id -> requester.requester_id` | 1 : N | optional |
| purchase_request | exception_register | `exception_register.pr_id -> purchase_request.pr_id` | 1 : N | optional |
| approval | exception_register | `exception_register.approval_id -> approval.approval_id` | 1 : N | optional |

Many-to-many relationships are resolved through bridge tables: supplier <-> item_category (`supplier_category`), RFQ <-> supplier (`rfq_supplier`) and purchase request <-> purchase order (`po_line`, one row per ordered request line; direct-buy POs can consolidate several requests).

## department

Organisational unit that owns budgets and requesters.  
*Kind:* Master data. *Primary key:* `department_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| department_id | TEXT | Y | `DEPT-\d{3}` |  | Y |  | Department key. |
| department_name | TEXT | Y |  |  | Y |  | Department name. |
| cost_center | TEXT | Y | `CC-\d{4}` |  | Y |  | Finance cost centre code. |
| division | TEXT | Y | CORPORATE, TECHNOLOGY, OPERATIONS, COMMERCIAL |  |  |  | Division used to resolve the VP approver. |
| status | TEXT | Y | ACTIVE, INACTIVE |  |  |  | Lifecycle state. |
| effective_from | DATE | Y |  |  |  |  | Date the department record became effective. |

## requester

Employee who can raise requests; approvers, buyers and controllers are requesters with elevated roles.  
*Kind:* Master data. *Primary key:* `requester_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| requester_id | TEXT | Y | `EMP-\d{5}` |  | Y |  | Employee key. |
| full_name | TEXT | Y |  |  |  |  | Synthetic person name. |
| email | TEXT | Y |  |  | Y | ends with @example.com | Synthetic e-mail on the reserved example.com domain. |
| department_id | TEXT | Y | `DEPT-\d{3}` |  |  | FK department.department_id | Home department. |
| job_title | TEXT | Y |  |  |  |  | Job title. |
| role | TEXT | Y | CEO, CFO, VP, DIRECTOR, MANAGER, STAFF, BUYER, FINANCE_CONTROLLER |  |  |  | Approval / workflow role. |
| approval_limit_usd | DECIMAL(14,2) |  |  | USD |  |  | Spend limit for approver roles; null for non-approvers. |
| manager_id | TEXT |  | `EMP-\d{5}` |  |  | FK requester.requester_id | Line manager (self reference); null for the CEO. |
| hire_date | DATE | Y |  |  |  |  | Employment start (effective_from). |
| termination_date | DATE |  |  |  |  | >= hire_date | Employment end (effective_to); null while employed. |
| status | TEXT | Y | ACTIVE, INACTIVE |  |  | derived | Status at the snapshot date. |

## item_category

Spend category; drives budget type, duty and lead time.  
*Kind:* Reference data. *Primary key:* `category_code`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| category_code | TEXT | Y | `[A-Z][A-Z_]+` |  | Y |  | Category key. |
| category_name | TEXT | Y |  |  | Y |  | Category name. |
| budget_type | TEXT | Y | OPEX, CAPEX |  |  |  | Budget the spend is charged to. |
| is_service | BOOLEAN | Y |  |  |  |  | True for services (domestic suppliers only). |
| import_duty_rate | DECIMAL(6,4) | Y |  | fraction |  | 0 <= x < 0.2 | Duty applied to non-domestic, non-DDP quotes. |
| standard_lead_time_days | INTEGER | Y |  | days |  | > 0 | Typical supplier lead time. |

## supplier

Vendor master. Status and risk are effective-dated in child tables; the columns here are the snapshot values.  
*Kind:* Master data. *Primary key:* `supplier_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| supplier_id | TEXT | Y | `SUP\d{4}` |  | Y |  | Supplier key; also the <supplier-code> used in quote IDs. |
| supplier_name | TEXT | Y |  |  | Y |  | Synthetic legal name. |
| country_code | TEXT | Y | US, CA, MX, DE, GB, IN, CN |  |  |  | ISO country. |
| currency_code | TEXT | Y | USD, EUR, GBP, CAD, MXN, INR, CNY |  |  |  | Supplier's home currency. |
| supplier_tier | TEXT | Y | STRATEGIC, PREFERRED, APPROVED |  |  |  | Relationship tier. |
| payment_terms | TEXT | Y | NET30, NET45, NET60 |  |  |  | Default payment terms. |
| default_incoterm | TEXT | Y | DDP, DAP, FCA, FOB, EXW |  |  |  | Default delivery term. |
| onboarded_date | DATE | Y |  |  |  |  | Date first approved as a vendor. |
| status | TEXT | Y | ACTIVE, SUSPENDED, INACTIVE |  |  | derived | Status at the snapshot (latest status history row). |
| risk_rating | TEXT | Y | NONE, LOW, MEDIUM, HIGH |  |  | derived | Highest severity of risk flags open at the snapshot. |
| contact_email | TEXT | Y |  |  | Y |  | Synthetic RFQ mailbox. |

## item

Catalogue item with a list price used for estimates and contract pricing.  
*Kind:* Reference data. *Primary key:* `item_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| item_id | TEXT | Y | `ITM-\d{5}` |  | Y |  | Item key. |
| item_name | TEXT | Y |  |  | Y |  | Item description. |
| category_code | TEXT | Y |  |  |  | FK item_category.category_code | Category. |
| uom | TEXT | Y | EA, BOX, PK, KG, ROLL, LIC, HR |  |  |  | Unit of measure. |
| list_price_usd | DECIMAL(14,2) | Y |  | USD |  | > 0 | Catalogue list price. |
| is_sole_source | BOOLEAN | Y |  |  |  |  | Only one supplier (the OEM) can supply this item. |
| sole_source_supplier_id | TEXT |  | `SUP\d{4}` |  |  | FK supplier.supplier_id | OEM supplier; required when is_sole_source. |

## supplier_category

N:M bridge - which suppliers serve which categories, with contract preference.  
*Kind:* Bridge (N:M). *Primary key:* `supplier_id, category_code`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| supplier_id | TEXT | Y | `SUP\d{4}` |  |  | FK supplier.supplier_id | Supplier. |
| category_code | TEXT | Y |  |  |  | FK item_category.category_code | Category. |
| preference_rank | INTEGER |  | 1, 2 |  |  |  | 1 = primary contract supplier, 2 = secondary; null = approved only. |
| contract_discount_pct | DECIMAL(6,4) |  |  | fraction |  | required when preference_rank is set | Discount off list price for contract (direct) buys. |
| effective_from | DATE | Y |  |  |  |  | Date the supplier was approved for the category. |

## supplier_status_history

Effective-dated supplier status; half-open interval [effective_from, effective_to).  
*Kind:* Event / history (append-only). *Primary key:* `status_history_id`. *Natural keys:* (supplier_id, effective_from).

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| status_history_id | TEXT | Y | `SSH-\d{6}` |  | Y |  | Row key. |
| supplier_id | TEXT | Y | `SUP\d{4}` |  |  | FK supplier.supplier_id | Supplier. |
| status | TEXT | Y | ACTIVE, SUSPENDED, INACTIVE |  |  |  | Status during the interval. |
| effective_from | DATE | Y |  |  |  |  | Interval start (inclusive). |
| effective_to | DATE |  |  |  |  | > effective_from | Interval end (exclusive); null = current. |
| reason_code | TEXT | Y | ONBOARDED, CONTRACT_TERMINATED, MERGED_ACQUIRED, COMPLIANCE_REVIEW, COMPLIANCE_FAILURE, VOLUNTARY_EXIT, REINSTATED |  |  |  | Why the status changed. |

## supplier_risk_flag

Risk signals raised against a supplier (effective-dated).  
*Kind:* Event / history (append-only). *Primary key:* `risk_flag_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| risk_flag_id | TEXT | Y | `SRF-\d{6}` |  | Y |  | Row key. |
| supplier_id | TEXT | Y | `SUP\d{4}` |  |  | FK supplier.supplier_id | Supplier. |
| flag_type | TEXT | Y | FINANCIAL_DISTRESS, SANCTIONS_SCREENING_HIT, QUALITY_ISSUE, DELIVERY_PERFORMANCE, CYBER_INCIDENT, ESG_CONCERN |  |  |  | Risk type. |
| severity | TEXT | Y | LOW, MEDIUM, HIGH |  |  |  | HIGH excludes the supplier from invitations and awards. |
| raised_date | DATE | Y |  |  |  |  | Date raised. |
| cleared_date | DATE |  |  |  |  | > raised_date | Date cleared; null = still open. |
| source | TEXT | Y | CREDIT_MONITORING, SANCTIONS_SCREENING, QUALITY_AUDIT, SUPPLIER_SCORECARD, NEWS_MONITORING |  |  |  | Origin of the signal. |

## fx_rate

Synthetic monthly FX table (USD per unit of currency).  
*Kind:* Reference data. *Primary key:* `currency_code, rate_month`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| currency_code | TEXT | Y | USD, EUR, GBP, CAD, MXN, INR, CNY |  |  |  | Currency. |
| rate_month | TEXT | Y | `2026-\d{2}` |  |  |  | Month the rate applies to. |
| usd_per_unit | DECIMAL(12,6) | Y |  | USD per unit |  | > 0; USD = 1 | Conversion rate. |

## budget

Annual FY2026 budget per department and budget type, plus one corporate contingency pool.  
*Kind:* Master data. *Primary key:* `budget_id`. *Natural keys:* (department_id, fiscal_year, budget_type).

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| budget_id | TEXT | Y | `BUD-2026-\d{4}` |  | Y |  | Budget key. |
| department_id | TEXT | Y | `DEPT-\d{3}` |  |  | FK department.department_id | Owning department. |
| fiscal_year | INTEGER | Y | 2026 |  |  |  | Fiscal year. |
| budget_type | TEXT | Y | OPEX, CAPEX, CONTINGENCY |  |  |  | Budget class. |
| allocated_amount_usd | DECIMAL(14,2) | Y |  | USD |  | > 0 | Original allocation (transfers are in budget_transaction). |
| owner_id | TEXT | Y | `EMP-\d{5}` |  |  | FK requester.requester_id | Accountable budget owner. |
| effective_from | DATE | Y |  |  |  |  | Budget period start. |
| effective_to | DATE | Y |  |  |  | > effective_from | Budget period end. |
| status | TEXT | Y | OPEN, CLOSED |  |  |  | Lifecycle state. |

## purchase_request

Purchase request (PR) header.  
*Kind:* Transaction. *Primary key:* `pr_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| pr_id | TEXT | Y | `PR-2026-\d{6}` |  | Y |  | Request key, assigned in submission order. |
| requester_id | TEXT | Y | `EMP-\d{5}` |  |  | FK requester.requester_id | Requester (active at submission). |
| department_id | TEXT | Y | `DEPT-\d{3}` |  |  | FK department.department_id | Requester department. |
| budget_id | TEXT | Y | `BUD-2026-\d{4}` |  |  | FK budget.budget_id | Budget charged (department x category budget type). |
| category_code | TEXT | Y |  |  |  | FK item_category.category_code | Single spend category of all lines. |
| submitted_at | TIMESTAMP | Y |  |  |  |  | Submission time (working hours). |
| need_by_date | DATE | Y |  |  |  | > submitted_at | Date the goods/services are needed. |
| priority | TEXT | Y | LOW, MEDIUM, HIGH, CRITICAL |  |  |  | Business priority. |
| justification | TEXT |  |  |  |  |  | Business justification; empty triggers rejection rule R-JUST. |
| sourcing_route | TEXT | Y | DIRECT, COMPETITIVE_RFQ, SINGLE_SOURCE_RFQ |  |  | derived | Rule SRC-1: >= 10,000 USD -> RFQ; OEM-only item or emergency -> single source. |
| estimated_total_usd | DECIMAL(14,2) | Y |  | USD |  | derived | Sum of request line totals. |
| budget_checked_at | TIMESTAMP |  |  |  |  | derived | When the budget check ran (approval chain start). |
| budget_available_usd | DECIMAL(14,2) |  |  | USD |  | derived | Available budget excluding this request's own reservation at the check. |
| budget_check_result | TEXT |  | WITHIN_BUDGET, OVER_BUDGET |  |  | derived | Outcome of the budget check. |
| approval_basis_usd | DECIMAL(14,2) |  |  | USD |  | derived | Amount the thresholds were applied to (estimate for direct, awarded landed cost for RFQ). |
| approval_tier | INTEGER |  | 1, 2, 3, 4 |  |  | derived | Threshold tier 1-4 (APR-T1..T4). |
| status | TEXT | Y | SUBMITTED, SOURCING, PENDING_APPROVAL, APPROVED, REJECTED, CANCELLED, ORDERED, PARTIALLY_RECEIVED, RECEIVED, CLOSED_SHORT |  |  | derived | Current lifecycle state (= last status_event). |
| status_updated_at | TIMESTAMP | Y |  |  |  | derived | Time of the last status change. |

## request_line

Request line: item, quantity and the requester estimate.  
*Kind:* Transaction. *Primary key:* `pr_line_id`. *Natural keys:* (pr_id, line_no).

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| pr_line_id | TEXT | Y | `PR-2026-\d{6}-L\d{2}` |  | Y |  | Line key = <pr_id>-Lnn. |
| pr_id | TEXT | Y | `PR-2026-\d{6}` |  |  | FK purchase_request.pr_id | Parent request. |
| line_no | INTEGER | Y |  |  |  | >= 1 | Line number. |
| item_id | TEXT | Y | `ITM-\d{5}` |  |  | FK item.item_id | Catalogue item (same category as header). |
| quantity | INTEGER | Y |  | uom |  | > 0 | Requested quantity. |
| uom | TEXT | Y | EA, BOX, PK, KG, ROLL, LIC, HR |  |  |  | Unit of measure (= item uom). |
| est_unit_price_usd | DECIMAL(14,2) | Y |  | USD |  | > 0 | Requester estimate per unit. |
| est_line_total_usd | DECIMAL(14,2) | Y |  | USD |  | derived | quantity x est_unit_price_usd. |

## rfq

Request for quotation; exactly one per request in the RFQ routes (1:0..1).  
*Kind:* Transaction. *Primary key:* `rfq_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| rfq_id | TEXT | Y | `RFQ-2026-\d{6}` |  | Y |  | RFQ key, assigned in issue order. |
| pr_id | TEXT | Y | `PR-2026-\d{6}` |  | Y | FK purchase_request.pr_id | Request being sourced. |
| buyer_id | TEXT | Y | `EMP-\d{5}` |  |  | FK requester.requester_id | Responsible buyer (role BUYER). |
| sourcing_type | TEXT | Y | COMPETITIVE, SINGLE_SOURCE |  |  |  | Competitive (>= 3 quotes) or single source. |
| single_source_reason | TEXT |  | SOLE_SOURCE_OEM, EMERGENCY |  |  |  | Required for SINGLE_SOURCE. |
| currency_code | TEXT | Y | USD |  |  |  | Currency bids are requested in. |
| issued_at | TIMESTAMP | Y |  |  |  | >= request submitted_at | Issue time. |
| response_due_at | TIMESTAMP | Y |  |  |  | > issued_at | Bid deadline. |
| min_quotes_required | INTEGER | Y | 1, 3 |  |  |  | 3 for competitive, 1 for single source. |
| evaluated_at | TIMESTAMP |  |  |  |  | >= response_due_at | When quotes were evaluated; null while open. |
| status | TEXT | Y | OPEN, UNDER_EVALUATION, AWARD_RECOMMENDED, AWARDED, AWARD_REJECTED, CANCELLED |  |  | derived | Current lifecycle state. |
| cancel_reason | TEXT |  | REQUIREMENT_WITHDRAWN, NO_ELIGIBLE_QUOTES, AWARDED_SUPPLIER_INACTIVE |  |  |  | Required when CANCELLED. |
| quotes_received | INTEGER | Y |  |  |  | derived | Count of supplier_quote rows. |

## rfq_supplier

N:M bridge - suppliers invited to an RFQ and their response.  
*Kind:* Bridge (N:M). *Primary key:* `rfq_id, supplier_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| rfq_id | TEXT | Y | `RFQ-2026-\d{6}` |  |  | FK rfq.rfq_id | RFQ. |
| supplier_id | TEXT | Y | `SUP\d{4}` |  |  | FK supplier.supplier_id | Invited supplier (active, serves the category, no open HIGH risk flag). |
| invited_at | TIMESTAMP | Y |  |  |  |  | Invitation time (= RFQ issue). |
| response_status | TEXT | Y | QUOTED, DECLINED, NO_RESPONSE, PENDING |  |  |  | Response. |
| responded_at | TIMESTAMP |  |  |  |  |  | Response time for QUOTED / DECLINED. |

## supplier_quote

Supplier quote header (one per invited supplier that bid).  
*Kind:* Transaction. *Primary key:* `quote_id`. *Natural keys:* (rfq_id, supplier_id).

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| quote_id | TEXT | Y | `QUO-SUP\d{4}-2026-\d{6}` |  | Y |  | QUO-<supplier-code>-2026-nnnnnn; global counter in submission order. |
| rfq_id | TEXT | Y | `RFQ-2026-\d{6}` |  |  | FK rfq.rfq_id | RFQ answered. |
| supplier_id | TEXT | Y | `SUP\d{4}` |  |  | FK supplier.supplier_id | Bidding supplier (must be invited). |
| submitted_at | TIMESTAMP | Y |  |  |  | issued_at <= x <= response_due_at | Submission time. |
| valid_until | DATE | Y |  |  |  | >= submitted date | Last date the price is valid. |
| currency_code | TEXT | Y | USD, EUR, GBP, CAD, MXN, INR, CNY |  |  |  | Currency the quote is priced in. |
| incoterm | TEXT | Y | DDP, DAP, FCA, FOB, EXW |  |  |  | Delivery term; DDP includes freight and duty in price. |
| lead_time_days | INTEGER | Y |  | days |  | > 0 | Promised lead time from PO. |
| goods_amount | DECIMAL(14,2) | Y |  | quote currency |  | derived | Sum of quote lines. |
| freight_amount | DECIMAL(14,2) | Y |  | quote currency |  | >= 0 | Freight charge. |
| total_amount | DECIMAL(14,2) | Y |  | quote currency |  | derived | goods_amount + freight_amount. |
| status | TEXT | Y | RECEIVED, SELECTED, NOT_SELECTED, DISQUALIFIED, AWARDED, AWARD_REJECTED, CANCELLED |  |  | derived | Current lifecycle state. |

## quote_line

Quoted price per request line.  
*Kind:* Transaction. *Primary key:* `quote_line_id`. *Natural keys:* (quote_id, pr_line_id).

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| quote_line_id | TEXT | Y | `QUO-SUP\d{4}-2026-\d{6}-L\d{2}` |  | Y |  | <quote_id>-Lnn. |
| quote_id | TEXT | Y | `QUO-SUP\d{4}-2026-\d{6}` |  |  | FK supplier_quote.quote_id | Parent quote. |
| pr_line_id | TEXT | Y | `PR-2026-\d{6}-L\d{2}` |  |  | FK request_line.pr_line_id | Request line priced (belongs to the RFQ request). |
| line_no | INTEGER | Y |  |  |  | >= 1 | Line number. |
| quantity | INTEGER | Y |  |  |  | > 0 | Quoted quantity (= request quantity). |
| unit_price | DECIMAL(14,2) | Y |  |  |  | > 0 | Unit price in quote currency. |
| line_amount | DECIMAL(14,2) | Y |  |  |  | derived | quantity x unit_price. |

## quote_evaluation

Buyer comparison record per quote: landed cost, delivery and eligibility (1:1 with evaluated quotes).  
*Kind:* Derived. *Primary key:* `quote_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| quote_id | TEXT | Y | `QUO-SUP\d{4}-2026-\d{6}` |  | Y | FK supplier_quote.quote_id | Quote evaluated. |
| rfq_id | TEXT | Y | `RFQ-2026-\d{6}` |  |  | FK rfq.rfq_id | RFQ. |
| evaluated_at | TIMESTAMP | Y |  |  |  |  | Evaluation time (= rfq.evaluated_at). |
| fx_rate_used | DECIMAL(12,6) | Y |  | USD per unit |  |  | USD per unit used for conversion (fx_rate of the quote month). |
| goods_usd | DECIMAL(14,2) | Y |  | USD |  | derived | goods_amount x fx_rate_used. |
| freight_usd | DECIMAL(14,2) | Y |  | USD |  | derived | freight_amount x fx_rate_used. |
| duty_usd | DECIMAL(14,2) | Y |  | USD |  | derived | goods_usd x import_duty_rate when supplier is non-US and incoterm != DDP. |
| landed_cost_usd | DECIMAL(14,2) | Y |  | USD |  | derived | goods_usd + freight_usd + duty_usd. |
| expected_delivery_date | DATE | Y |  |  |  | derived | evaluation date + 2 business days + lead_time_days. |
| meets_need_by | BOOLEAN | Y |  |  |  | derived | expected_delivery_date <= request need_by_date. |
| is_valid_at_evaluation | BOOLEAN | Y |  |  |  | derived | valid_until >= evaluation date. |
| supplier_status_at_evaluation | TEXT | Y | ACTIVE, SUSPENDED, INACTIVE |  |  | derived | From supplier_status_history. |
| supplier_risk_at_evaluation | TEXT | Y | NONE, LOW, MEDIUM, HIGH |  |  | derived | Highest open risk flag severity. |
| is_eligible | BOOLEAN | Y |  |  |  | derived | Valid AND supplier ACTIVE AND risk != HIGH. |
| disqualification_reason | TEXT |  | EXPIRED, SUPPLIER_INACTIVE, SUPPLIER_HIGH_RISK |  |  |  | Why ineligible. |
| landed_cost_rank | INTEGER |  |  |  |  | derived | Rank among eligible quotes (1 = cheapest). |

## rfq_award

Award recommendation (decision record) for an RFQ (1:0..1).  
*Kind:* Transaction. *Primary key:* `rfq_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| rfq_id | TEXT | Y | `RFQ-2026-\d{6}` |  | Y | FK rfq.rfq_id | RFQ. |
| quote_id | TEXT | Y | `QUO-SUP\d{4}-2026-\d{6}` |  | Y | FK supplier_quote.quote_id | Selected quote. |
| supplier_id | TEXT | Y | `SUP\d{4}` |  |  | FK supplier.supplier_id | Selected supplier (= quote supplier). |
| buyer_id | TEXT | Y | `EMP-\d{5}` |  |  | FK requester.requester_id | Buyer recommending the award. |
| recommended_at | TIMESTAMP | Y |  |  |  |  | Decision time (= rfq.evaluated_at). |
| award_basis | TEXT |  | LOWEST_LANDED_COST, DELIVERY_REQUIREMENT, RISK_MITIGATION, SOLE_SOURCE |  |  |  | Rule AWD-1..4 that justified the selection. |
| award_rationale | TEXT |  |  |  |  |  | Mandatory narrative when the selection is not the lowest landed cost. |
| awarded_landed_cost_usd | DECIMAL(14,2) | Y |  | USD |  |  | Landed cost of the selected quote as evaluated. |
| status | TEXT | Y | PENDING_APPROVAL, APPROVED, REJECTED, WITHDRAWN |  |  | derived | Approval outcome of the award. |
| decided_at | TIMESTAMP |  |  |  |  | derived | When the approval chain finished. |

## approval

One row per approval step requested. Steps are sequential; history is never overwritten.  
*Kind:* Event / history (append-only). *Primary key:* `approval_id`. *Natural keys:* (pr_id, rfq_id, approval_type, approval_level, step_no).

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| approval_id | TEXT | Y | `APR-2026-\d{6}` |  | Y |  | Approval step key, assigned in request order. |
| pr_id | TEXT | Y | `PR-2026-\d{6}` |  |  | FK purchase_request.pr_id | Request being approved. |
| rfq_id | TEXT |  | `RFQ-2026-\d{6}` |  |  | FK rfq.rfq_id | Set when approving an RFQ award. |
| approval_type | TEXT | Y | SPEND, BUDGET_EXCEPTION, SINGLE_SOURCE, COMPETITION_WAIVER |  |  |  | SPEND = threshold chain; others are exception approvals. |
| approval_level | TEXT | Y | MANAGER, DIRECTOR, VP, CFO, FINANCE_CONTROLLER, PROCUREMENT_DIRECTOR |  |  |  | Authority level required by the rule. |
| step_no | INTEGER | Y |  |  |  | >= 1 | Order within the chain. |
| approver_id | TEXT | Y | `EMP-\d{5}` |  |  | FK requester.requester_id | Resolved approver (never the requester). |
| basis_amount_usd | DECIMAL(14,2) | Y |  | USD |  |  | Amount under approval. |
| rule_id | TEXT | Y |  |  |  |  | Rule that required the step (APR-T1..T4, BUD-EXC, SRC-SS, SRC-WAIVER). |
| requested_at | TIMESTAMP | Y |  |  |  |  | When the step was routed. |
| decided_at | TIMESTAMP |  |  |  |  | >= requested_at | Decision time; null while PENDING. |
| decision | TEXT | Y | PENDING, APPROVED, REJECTED, WITHDRAWN |  |  |  | Outcome. |
| decision_reason | TEXT |  | WITHIN_POLICY, INSUFFICIENT_JUSTIFICATION, BUDGET_EXCEEDED, CONTINGENCY_EXHAUSTED, LOW_PRIORITY_DEFERRED, CFO_DEFERRED, JUSTIFICATION_ACCEPTED, REQUEST_WITHDRAWN |  |  |  | Reason code (required unless PENDING). |
| comment | TEXT |  |  |  |  |  | Approver comment. |

## purchase_order

Purchase order header. RFQ POs copy the awarded quote; direct POs use contract pricing.  
*Kind:* Transaction. *Primary key:* `po_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| po_id | TEXT | Y | `PO-2026-\d{6}` |  | Y |  | PO key, assigned in issue order. |
| supplier_id | TEXT | Y | `SUP\d{4}` |  |  | FK supplier.supplier_id | Supplier ordered from. |
| department_id | TEXT | Y | `DEPT-\d{3}` |  |  | FK department.department_id | Ordering department. |
| budget_id | TEXT | Y | `BUD-2026-\d{4}` |  |  | FK budget.budget_id | Budget committed. |
| buyer_id | TEXT | Y | `EMP-\d{5}` |  |  | FK requester.requester_id | Buyer who issued the PO. |
| source_type | TEXT | Y | RFQ_AWARD, DIRECT_CONTRACT |  |  |  | RFQ_AWARD (1 PO per awarded RFQ) or DIRECT_CONTRACT (may consolidate requests). |
| rfq_id | TEXT |  | `RFQ-2026-\d{6}` |  |  | FK rfq.rfq_id | RFQ for RFQ_AWARD POs. |
| quote_id | TEXT |  | `QUO-SUP\d{4}-2026-\d{6}` |  |  | FK supplier_quote.quote_id | Awarded quote for RFQ_AWARD POs. |
| issued_at | TIMESTAMP | Y |  |  |  |  | Issue time. |
| currency_code | TEXT | Y | USD, EUR, GBP, CAD, MXN, INR, CNY |  |  |  | PO currency (must equal the awarded quote currency). |
| payment_terms | TEXT | Y | NET30, NET45, NET60 |  |  |  | Payment terms. |
| incoterm | TEXT | Y | DDP, DAP, FCA, FOB, EXW |  |  |  | Delivery term. |
| promised_date | DATE | Y |  |  |  | derived | issue date + lead time. |
| goods_amount | DECIMAL(14,2) | Y |  | PO currency |  | derived | Sum of PO lines. |
| freight_amount | DECIMAL(14,2) | Y |  | PO currency |  |  | Freight (from quote; 0 for direct). |
| total_amount | DECIMAL(14,2) | Y |  | PO currency |  | derived | goods_amount + freight_amount. |
| fx_rate_to_usd | DECIMAL(12,6) | Y |  | USD per unit |  |  | fx_rate of the issue month. |
| est_duty_usd | DECIMAL(14,2) | Y |  | USD |  | derived | Estimated import duty. |
| total_usd | DECIMAL(14,2) | Y |  | USD |  | derived | total_amount x fx_rate_to_usd + est_duty_usd; the budget commitment. |
| status | TEXT | Y | ISSUED, PARTIALLY_RECEIVED, RECEIVED, CLOSED_SHORT |  |  | derived | Current lifecycle state. |
| closed_at | TIMESTAMP |  |  |  |  | derived | When fully received or short-closed. |

## po_line

PO line; also the bridge between POs and request lines (PR:PO is N:M).  
*Kind:* Transaction. *Primary key:* `po_line_id`. *Natural keys:* (po_id, line_no).

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| po_line_id | TEXT | Y | `PO-2026-\d{6}-L\d{2}` |  | Y |  | <po_id>-Lnn. |
| po_id | TEXT | Y | `PO-2026-\d{6}` |  |  | FK purchase_order.po_id | Parent PO. |
| line_no | INTEGER | Y |  |  |  | >= 1 | Line number. |
| pr_id | TEXT | Y | `PR-2026-\d{6}` |  |  | FK purchase_request.pr_id | Request the line fulfils. |
| pr_line_id | TEXT | Y | `PR-2026-\d{6}-L\d{2}` |  | Y | FK request_line.pr_line_id | Request line fulfilled. |
| quote_line_id | TEXT |  | `QUO-SUP\d{4}-2026-\d{6}-L\d{2}` |  |  | FK quote_line.quote_line_id | Awarded quote line (RFQ POs). |
| item_id | TEXT | Y | `ITM-\d{5}` |  |  | FK item.item_id | Item. |
| quantity | INTEGER | Y |  |  |  | > 0 | Ordered quantity. |
| unit_price | DECIMAL(14,2) | Y |  |  |  | > 0 | Unit price in PO currency. |
| line_amount | DECIMAL(14,2) | Y |  |  |  | derived | quantity x unit_price. |
| qty_received | INTEGER | Y |  |  |  | derived | Sum of accepted delivery quantities. |
| line_status | TEXT | Y | OPEN, PARTIALLY_RECEIVED, RECEIVED, CLOSED_SHORT |  |  | derived | Receipt state. |

## delivery

Goods receipt / service acceptance event. Several per PO for partial deliveries.  
*Kind:* Event / history (append-only). *Primary key:* `delivery_id`. *Natural keys:* (po_id, delivery_seq).

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| delivery_id | TEXT | Y | `DEL-PO-2026-\d{6}-\d{2}` |  | Y |  | DEL-<po_id>-nn, numbered per PO in arrival order. |
| po_id | TEXT | Y | `PO-2026-\d{6}` |  |  | FK purchase_order.po_id | PO delivered against. |
| delivery_seq | INTEGER | Y |  |  |  | >= 1 | Sequence within the PO. |
| carrier | TEXT | Y |  |  |  |  | Carrier (synthetic). |
| delivered_at | TIMESTAMP | Y |  |  |  | >= po issued_at | Receipt time. |
| received_by | TEXT | Y | `EMP-\d{5}` |  |  | FK requester.requester_id | Employee who receipted. |
| is_on_time | BOOLEAN | Y |  |  |  | derived | delivered date <= PO promised_date. |
| days_late | INTEGER | Y |  | days |  | derived | max(0, delivered date - promised_date). |
| completes_po | BOOLEAN | Y |  |  |  | derived | PO fully received after this delivery. |

## delivery_line

Quantities delivered, accepted and rejected per PO line.  
*Kind:* Event / history (append-only). *Primary key:* `delivery_line_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| delivery_line_id | TEXT | Y | `DEL-PO-2026-\d{6}-\d{2}-L\d{2}` |  | Y |  | <delivery_id>-Lnn. |
| delivery_id | TEXT | Y | `DEL-PO-2026-\d{6}-\d{2}` |  |  | FK delivery.delivery_id | Parent delivery. |
| po_line_id | TEXT | Y | `PO-2026-\d{6}-L\d{2}` |  |  | FK po_line.po_line_id | PO line. |
| qty_delivered | INTEGER | Y |  |  |  | > 0 | Delivered quantity. |
| qty_accepted | INTEGER | Y |  |  |  | qty_accepted + qty_rejected = qty_delivered | Accepted quantity. |
| qty_rejected | INTEGER | Y |  |  |  | >= 0 | Rejected at inspection. |
| rejection_reason | TEXT |  | DAMAGED, QUALITY_FAIL, WRONG_ITEM |  |  |  | Required when qty_rejected > 0. |

## budget_transaction

Append-only budget ledger; balances are sums of deltas.  
*Kind:* Event / history (append-only). *Primary key:* `budget_txn_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| budget_txn_id | TEXT | Y | `BTX-2026-\d{6}` |  | Y |  | Ledger key in time order. |
| budget_id | TEXT | Y | `BUD-2026-\d{4}` |  |  | FK budget.budget_id | Budget affected. |
| txn_ts | TIMESTAMP | Y |  |  |  |  | Posting time. |
| txn_type | TEXT | Y | RESERVE, RESERVE_ADJUST, RELEASE, COMMIT, DECOMMIT, TRANSFER_IN, TRANSFER_OUT |  |  |  | Ledger movement. |
| source_type | TEXT | Y | PURCHASE_REQUEST, PURCHASE_ORDER, APPROVAL |  |  |  | Document that caused the posting. |
| source_id | TEXT | Y |  |  |  |  | Polymorphic reference: pr_id, po_id or approval_id per source_type. |
| allocated_delta_usd | DECIMAL(14,2) | Y |  | USD |  |  | Change to allocation (transfers). |
| reserved_delta_usd | DECIMAL(14,2) | Y |  | USD |  |  | Change to reserved (pre-encumbrance). |
| committed_delta_usd | DECIMAL(14,2) | Y |  | USD |  |  | Change to committed (PO encumbrance). |
| note | TEXT |  |  |  |  |  | Narrative. |

## budget_balance

Snapshot balances recomputed from budget + budget_transaction.  
*Kind:* Derived. *Primary key:* `budget_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| budget_id | TEXT | Y | `BUD-2026-\d{4}` |  | Y | FK budget.budget_id | Budget. |
| allocated_original_usd | DECIMAL(14,2) | Y |  | USD |  | derived | budget.allocated_amount_usd. |
| transfers_net_usd | DECIMAL(14,2) | Y |  | USD |  | derived | Sum of allocated_delta_usd. |
| allocated_current_usd | DECIMAL(14,2) | Y |  | USD |  | derived | Original + transfers. |
| reserved_usd | DECIMAL(14,2) | Y |  | USD |  | derived | Sum of reserved_delta_usd. |
| committed_usd | DECIMAL(14,2) | Y |  | USD |  | derived | Sum of committed_delta_usd. |
| available_usd | DECIMAL(14,2) | Y |  | USD |  | derived | allocated_current - reserved - committed. |
| utilization_pct | DECIMAL(6,4) | Y |  | fraction |  | derived | (reserved + committed) / allocated_current. |

## status_event

Lifecycle history for requests, RFQs, quotes and POs (append-only).  
*Kind:* Event / history (append-only). *Primary key:* `event_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| event_id | TEXT | Y | `EVT-2026-\d{6}` |  | Y |  | Event key in time order. |
| entity_type | TEXT | Y | PURCHASE_REQUEST, RFQ, SUPPLIER_QUOTE, PURCHASE_ORDER |  |  |  | Entity whose state changed. |
| entity_id | TEXT | Y |  |  |  |  | Polymorphic reference to the entity key. |
| from_status | TEXT |  |  |  |  |  | Previous state; null for creation. |
| to_status | TEXT | Y |  |  |  |  | New state. |
| event_ts | TIMESTAMP | Y |  |  |  |  | Transition time. |
| actor_id | TEXT |  | `EMP-\d{5}` |  |  | FK requester.requester_id | Employee who caused the change; null for supplier/system events. |
| reason | TEXT |  |  |  |  |  | Reason / reference. |

## exception_register

Documented business exceptions with reason and audit references (not anomaly labels).  
*Kind:* Derived. *Primary key:* `exception_id`.

| Column | Type | Req. | Allowed values / format | Unit | Unique | Rule / reference | Description |
|---|---|:-:|---|---|:-:|---|---|
| exception_id | TEXT | Y | `EXC-2026-\d{6}` |  | Y |  | Exception key. |
| exception_type | TEXT | Y | BUDGET_EXCEPTION, SINGLE_SOURCE, COMPETITION_WAIVER, NON_LOWEST_AWARD, QUOTE_EXPIRED, SUPPLIER_DISQUALIFIED, LATE_DELIVERY, PARTIAL_DELIVERY, QUALITY_REJECTION, SHORT_CLOSE |  |  |  | Exception class. |
| entity_type | TEXT | Y | PURCHASE_REQUEST, RFQ, SUPPLIER_QUOTE, PURCHASE_ORDER, DELIVERY |  |  |  | Entity the exception is about. |
| entity_id | TEXT | Y |  |  |  |  | Polymorphic reference. |
| pr_id | TEXT |  | `PR-2026-\d{6}` |  |  | FK purchase_request.pr_id | Related request. |
| raised_at | TIMESTAMP | Y |  |  |  |  | When raised. |
| reason_code | TEXT | Y |  |  |  |  | Machine-readable reason. |
| reason_text | TEXT | Y |  |  |  |  | Human-readable reason. |
| approval_id | TEXT |  | `APR-2026-\d{6}` |  |  | FK approval.approval_id | Approval that authorised it, when one is required. |
| resolution | TEXT | Y | APPROVED, REJECTED, PENDING, WITHDRAWN, EXCLUDED, RECORDED |  |  |  | Outcome. |
| resolved_at | TIMESTAMP |  |  |  |  |  | When resolved. |

## ground_truth (separate folder, never joined into inputs)

| Column | Description |
|---|---|
| gt_id | Label key GT-nnnnn. |
| issue_type | Anomaly class (one of the 7 required edge cases or SPLIT_PURCHASE). |
| sub_type | Variant of the anomaly. |
| severity | HIGH / MEDIUM / LOW. |
| entity_type | Primary entity labelled. |
| entity_id | Primary entity key. |
| related_ids | Pipe-separated keys of related records. |
| control_rule | Control that is violated. |
| expected_handling | What the process should have done. |
| description | Narrative. |
| evidence | JSON with the values that prove the anomaly. |
