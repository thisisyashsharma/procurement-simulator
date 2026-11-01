"""Single source of truth for tables, columns, keys and allowed values.

Drives the data dictionary, the SQL DDL and the generic validation checks.
"""
from __future__ import annotations

from dataclasses import dataclass

from .catalog_data import DIVISIONS, UOMS

ROLES = ("CEO", "CFO", "VP", "DIRECTOR", "MANAGER", "STAFF", "BUYER", "FINANCE_CONTROLLER")
PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
CURRENCIES = ("USD", "EUR", "GBP", "CAD", "MXN", "INR", "CNY")
COUNTRIES = ("US", "CA", "MX", "DE", "GB", "IN", "CN")
INCOTERMS = ("DDP", "DAP", "FCA", "FOB", "EXW")
SUPPLIER_STATUS = ("ACTIVE", "SUSPENDED", "INACTIVE")
RISK_LEVELS = ("NONE", "LOW", "MEDIUM", "HIGH")
PR_STATUS = ("SUBMITTED", "SOURCING", "PENDING_APPROVAL", "APPROVED", "REJECTED", "CANCELLED",
             "ORDERED", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED_SHORT")
RFQ_STATUS = ("OPEN", "UNDER_EVALUATION", "AWARD_RECOMMENDED", "AWARDED", "AWARD_REJECTED", "CANCELLED")
QUOTE_STATUS = ("RECEIVED", "SELECTED", "NOT_SELECTED", "DISQUALIFIED", "AWARDED", "AWARD_REJECTED",
                "CANCELLED")
PO_STATUS = ("ISSUED", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED_SHORT")
APPROVAL_TYPES = ("SPEND", "BUDGET_EXCEPTION", "SINGLE_SOURCE", "COMPETITION_WAIVER")
APPROVAL_LEVELS = ("MANAGER", "DIRECTOR", "VP", "CFO", "FINANCE_CONTROLLER", "PROCUREMENT_DIRECTOR")
DECISIONS = ("PENDING", "APPROVED", "REJECTED", "WITHDRAWN")
DECISION_REASONS = ("WITHIN_POLICY", "INSUFFICIENT_JUSTIFICATION", "BUDGET_EXCEEDED",
                    "CONTINGENCY_EXHAUSTED", "LOW_PRIORITY_DEFERRED", "CFO_DEFERRED",
                    "JUSTIFICATION_ACCEPTED", "REQUEST_WITHDRAWN")
AWARD_BASIS = ("LOWEST_LANDED_COST", "DELIVERY_REQUIREMENT", "RISK_MITIGATION", "SOLE_SOURCE")
EVENT_ENTITIES = ("PURCHASE_REQUEST", "RFQ", "SUPPLIER_QUOTE", "PURCHASE_ORDER")
EXCEPTION_TYPES = ("BUDGET_EXCEPTION", "SINGLE_SOURCE", "COMPETITION_WAIVER", "NON_LOWEST_AWARD",
                   "QUOTE_EXPIRED", "SUPPLIER_DISQUALIFIED", "LATE_DELIVERY", "PARTIAL_DELIVERY",
                   "QUALITY_REJECTION", "SHORT_CLOSE")

YR = r"2026"
P = {
    "dept": r"DEPT-\d{3}", "emp": r"EMP-\d{5}", "sup": r"SUP\d{4}", "item": r"ITM-\d{5}",
    "bud": rf"BUD-{YR}-\d{{4}}", "pr": rf"PR-{YR}-\d{{6}}", "prl": rf"PR-{YR}-\d{{6}}-L\d{{2}}",
    "rfq": rf"RFQ-{YR}-\d{{6}}", "quo": rf"QUO-SUP\d{{4}}-{YR}-\d{{6}}",
    "quol": rf"QUO-SUP\d{{4}}-{YR}-\d{{6}}-L\d{{2}}", "apr": rf"APR-{YR}-\d{{6}}",
    "po": rf"PO-{YR}-\d{{6}}", "pol": rf"PO-{YR}-\d{{6}}-L\d{{2}}",
    "del": rf"DEL-PO-{YR}-\d{{6}}-\d{{2}}", "dell": rf"DEL-PO-{YR}-\d{{6}}-\d{{2}}-L\d{{2}}",
    "btx": rf"BTX-{YR}-\d{{6}}", "evt": rf"EVT-{YR}-\d{{6}}", "exc": rf"EXC-{YR}-\d{{6}}",
    "ssh": r"SSH-\d{6}", "srf": r"SRF-\d{6}", "cat": r"[A-Z][A-Z_]+", "month": r"2026-\d{2}",
}
MONEY, RATE, PCT = "DECIMAL(14,2)", "DECIMAL(12,6)", "DECIMAL(6,4)"


@dataclass(frozen=True)
class Col:
    name: str
    type: str
    required: bool
    desc: str
    enum: tuple | None = None
    unit: str | None = None
    fk: str | None = None          # "table.column"
    pattern: str | None = None     # regex the value must fully match
    rule: str | None = None        # human readable validation rule
    derived: bool = False
    unique: bool = False


@dataclass(frozen=True)
class Table:
    name: str
    kind: str                      # master | reference | bridge | transaction | event | derived
    desc: str
    pk: tuple
    cols: tuple
    unique: tuple = ()             # composite natural keys


def C(name, type_, req, desc, **kw) -> Col:
    return Col(name, type_, req, desc, **kw)


def ID(name, pat, desc, **kw) -> Col:
    return Col(name, "TEXT", kw.pop("req", True), desc, pattern=P[pat], **kw)


TABLES: tuple[Table, ...] = (
    Table("department", "master", "Organisational unit that owns budgets and requesters.", ("department_id",), (
        ID("department_id", "dept", "Department key.", unique=True),
        C("department_name", "TEXT", True, "Department name.", unique=True),
        C("cost_center", "TEXT", True, "Finance cost centre code.", pattern=r"CC-\d{4}", unique=True),
        C("division", "TEXT", True, "Division used to resolve the VP approver.", enum=DIVISIONS),
        C("status", "TEXT", True, "Lifecycle state.", enum=("ACTIVE", "INACTIVE")),
        C("effective_from", "DATE", True, "Date the department record became effective."),
    )),
    Table("requester", "master", "Employee who can raise requests; approvers, buyers and controllers are requesters with elevated roles.", ("requester_id",), (
        ID("requester_id", "emp", "Employee key.", unique=True),
        C("full_name", "TEXT", True, "Synthetic person name."),
        C("email", "TEXT", True, "Synthetic e-mail on the reserved example.com domain.", unique=True, rule="ends with @example.com"),
        ID("department_id", "dept", "Home department.", fk="department.department_id"),
        C("job_title", "TEXT", True, "Job title."),
        C("role", "TEXT", True, "Approval / workflow role.", enum=ROLES),
        C("approval_limit_usd", MONEY, False, "Spend limit for approver roles; null for non-approvers.", unit="USD"),
        ID("manager_id", "emp", "Line manager (self reference); null for the CEO.", req=False, fk="requester.requester_id"),
        C("hire_date", "DATE", True, "Employment start (effective_from)."),
        C("termination_date", "DATE", False, "Employment end (effective_to); null while employed.", rule=">= hire_date"),
        C("status", "TEXT", True, "Status at the snapshot date.", enum=("ACTIVE", "INACTIVE"), derived=True),
    )),
    Table("item_category", "reference", "Spend category; drives budget type, duty and lead time.", ("category_code",), (
        C("category_code", "TEXT", True, "Category key.", pattern=P["cat"], unique=True),
        C("category_name", "TEXT", True, "Category name.", unique=True),
        C("budget_type", "TEXT", True, "Budget the spend is charged to.", enum=("OPEX", "CAPEX")),
        C("is_service", "BOOLEAN", True, "True for services (domestic suppliers only)."),
        C("import_duty_rate", PCT, True, "Duty applied to non-domestic, non-DDP quotes.", unit="fraction", rule="0 <= x < 0.2"),
        C("standard_lead_time_days", "INTEGER", True, "Typical supplier lead time.", unit="days", rule="> 0"),
    )),
    Table("supplier", "master", "Vendor master. Status and risk are effective-dated in child tables; the columns here are the snapshot values.", ("supplier_id",), (
        ID("supplier_id", "sup", "Supplier key; also the <supplier-code> used in quote IDs.", unique=True),
        C("supplier_name", "TEXT", True, "Synthetic legal name.", unique=True),
        C("country_code", "TEXT", True, "ISO country.", enum=COUNTRIES),
        C("currency_code", "TEXT", True, "Supplier's home currency.", enum=CURRENCIES),
        C("supplier_tier", "TEXT", True, "Relationship tier.", enum=("STRATEGIC", "PREFERRED", "APPROVED")),
        C("payment_terms", "TEXT", True, "Default payment terms.", enum=("NET30", "NET45", "NET60")),
        C("default_incoterm", "TEXT", True, "Default delivery term.", enum=INCOTERMS),
        C("onboarded_date", "DATE", True, "Date first approved as a vendor."),
        C("status", "TEXT", True, "Status at the snapshot (latest status history row).", enum=SUPPLIER_STATUS, derived=True),
        C("risk_rating", "TEXT", True, "Highest severity of risk flags open at the snapshot.", enum=RISK_LEVELS, derived=True),
        C("contact_email", "TEXT", True, "Synthetic RFQ mailbox.", unique=True),
    )),
    Table("item", "reference", "Catalogue item with a list price used for estimates and contract pricing.", ("item_id",), (
        ID("item_id", "item", "Item key.", unique=True),
        C("item_name", "TEXT", True, "Item description.", unique=True),
        C("category_code", "TEXT", True, "Category.", fk="item_category.category_code"),
        C("uom", "TEXT", True, "Unit of measure.", enum=UOMS),
        C("list_price_usd", MONEY, True, "Catalogue list price.", unit="USD", rule="> 0"),
        C("is_sole_source", "BOOLEAN", True, "Only one supplier (the OEM) can supply this item."),
        ID("sole_source_supplier_id", "sup", "OEM supplier; required when is_sole_source.", req=False, fk="supplier.supplier_id"),
    )),
    Table("supplier_category", "bridge", "N:M bridge - which suppliers serve which categories, with contract preference.", ("supplier_id", "category_code"), (
        ID("supplier_id", "sup", "Supplier.", fk="supplier.supplier_id"),
        C("category_code", "TEXT", True, "Category.", fk="item_category.category_code"),
        C("preference_rank", "INTEGER", False, "1 = primary contract supplier, 2 = secondary; null = approved only.", enum=(1, 2)),
        C("contract_discount_pct", PCT, False, "Discount off list price for contract (direct) buys.", unit="fraction", rule="required when preference_rank is set"),
        C("effective_from", "DATE", True, "Date the supplier was approved for the category."),
    )),
    Table("supplier_status_history", "event", "Effective-dated supplier status; half-open interval [effective_from, effective_to).", ("status_history_id",), (
        ID("status_history_id", "ssh", "Row key.", unique=True),
        ID("supplier_id", "sup", "Supplier.", fk="supplier.supplier_id"),
        C("status", "TEXT", True, "Status during the interval.", enum=SUPPLIER_STATUS),
        C("effective_from", "DATE", True, "Interval start (inclusive)."),
        C("effective_to", "DATE", False, "Interval end (exclusive); null = current.", rule="> effective_from"),
        C("reason_code", "TEXT", True, "Why the status changed.", enum=("ONBOARDED", "CONTRACT_TERMINATED", "MERGED_ACQUIRED", "COMPLIANCE_REVIEW", "COMPLIANCE_FAILURE", "VOLUNTARY_EXIT", "REINSTATED")),
    ), unique=(("supplier_id", "effective_from"),)),
    Table("supplier_risk_flag", "event", "Risk signals raised against a supplier (effective-dated).", ("risk_flag_id",), (
        ID("risk_flag_id", "srf", "Row key.", unique=True),
        ID("supplier_id", "sup", "Supplier.", fk="supplier.supplier_id"),
        C("flag_type", "TEXT", True, "Risk type.", enum=("FINANCIAL_DISTRESS", "SANCTIONS_SCREENING_HIT", "QUALITY_ISSUE", "DELIVERY_PERFORMANCE", "CYBER_INCIDENT", "ESG_CONCERN")),
        C("severity", "TEXT", True, "HIGH excludes the supplier from invitations and awards.", enum=("LOW", "MEDIUM", "HIGH")),
        C("raised_date", "DATE", True, "Date raised."),
        C("cleared_date", "DATE", False, "Date cleared; null = still open.", rule="> raised_date"),
        C("source", "TEXT", True, "Origin of the signal.", enum=("CREDIT_MONITORING", "SANCTIONS_SCREENING", "QUALITY_AUDIT", "SUPPLIER_SCORECARD", "NEWS_MONITORING")),
    )),
    Table("fx_rate", "reference", "Synthetic monthly FX table (USD per unit of currency).", ("currency_code", "rate_month"), (
        C("currency_code", "TEXT", True, "Currency.", enum=CURRENCIES),
        C("rate_month", "TEXT", True, "Month the rate applies to.", pattern=P["month"]),
        C("usd_per_unit", RATE, True, "Conversion rate.", unit="USD per unit", rule="> 0; USD = 1"),
    )),
    Table("budget", "master", "Annual FY2026 budget per department and budget type, plus one corporate contingency pool.", ("budget_id",), (
        ID("budget_id", "bud", "Budget key.", unique=True),
        ID("department_id", "dept", "Owning department.", fk="department.department_id"),
        C("fiscal_year", "INTEGER", True, "Fiscal year.", enum=(2026,)),
        C("budget_type", "TEXT", True, "Budget class.", enum=("OPEX", "CAPEX", "CONTINGENCY")),
        C("allocated_amount_usd", MONEY, True, "Original allocation (transfers are in budget_transaction).", unit="USD", rule="> 0"),
        ID("owner_id", "emp", "Accountable budget owner.", fk="requester.requester_id"),
        C("effective_from", "DATE", True, "Budget period start."),
        C("effective_to", "DATE", True, "Budget period end.", rule="> effective_from"),
        C("status", "TEXT", True, "Lifecycle state.", enum=("OPEN", "CLOSED")),
    ), unique=(("department_id", "fiscal_year", "budget_type"),)),
)

TABLES = TABLES + (
    Table("purchase_request", "transaction", "Purchase request (PR) header.", ("pr_id",), (
        ID("pr_id", "pr", "Request key, assigned in submission order.", unique=True),
        ID("requester_id", "emp", "Requester (active at submission).", fk="requester.requester_id"),
        ID("department_id", "dept", "Requester department.", fk="department.department_id"),
        ID("budget_id", "bud", "Budget charged (department x category budget type).", fk="budget.budget_id"),
        C("category_code", "TEXT", True, "Single spend category of all lines.", fk="item_category.category_code"),
        C("submitted_at", "TIMESTAMP", True, "Submission time (working hours)."),
        C("need_by_date", "DATE", True, "Date the goods/services are needed.", rule="> submitted_at"),
        C("priority", "TEXT", True, "Business priority.", enum=PRIORITIES),
        C("justification", "TEXT", False, "Business justification; empty triggers rejection rule R-JUST."),
        C("sourcing_route", "TEXT", True, "Rule SRC-1: >= 10,000 USD -> RFQ; OEM-only item or emergency -> single source.", enum=("DIRECT", "COMPETITIVE_RFQ", "SINGLE_SOURCE_RFQ"), derived=True),
        C("estimated_total_usd", MONEY, True, "Sum of request line totals.", unit="USD", derived=True),
        C("budget_checked_at", "TIMESTAMP", False, "When the budget check ran (approval chain start).", derived=True),
        C("budget_available_usd", MONEY, False, "Available budget excluding this request's own reservation at the check.", unit="USD", derived=True),
        C("budget_check_result", "TEXT", False, "Outcome of the budget check.", enum=("WITHIN_BUDGET", "OVER_BUDGET"), derived=True),
        C("approval_basis_usd", MONEY, False, "Amount the thresholds were applied to (estimate for direct, awarded landed cost for RFQ).", unit="USD", derived=True),
        C("approval_tier", "INTEGER", False, "Threshold tier 1-4 (APR-T1..T4).", enum=(1, 2, 3, 4), derived=True),
        C("status", "TEXT", True, "Current lifecycle state (= last status_event).", enum=PR_STATUS, derived=True),
        C("status_updated_at", "TIMESTAMP", True, "Time of the last status change.", derived=True),
    )),
    Table("request_line", "transaction", "Request line: item, quantity and the requester estimate.", ("pr_line_id",), (
        ID("pr_line_id", "prl", "Line key = <pr_id>-Lnn.", unique=True),
        ID("pr_id", "pr", "Parent request.", fk="purchase_request.pr_id"),
        C("line_no", "INTEGER", True, "Line number.", rule=">= 1"),
        ID("item_id", "item", "Catalogue item (same category as header).", fk="item.item_id"),
        C("quantity", "INTEGER", True, "Requested quantity.", unit="uom", rule="> 0"),
        C("uom", "TEXT", True, "Unit of measure (= item uom).", enum=UOMS),
        C("est_unit_price_usd", MONEY, True, "Requester estimate per unit.", unit="USD", rule="> 0"),
        C("est_line_total_usd", MONEY, True, "quantity x est_unit_price_usd.", unit="USD", derived=True),
    ), unique=(("pr_id", "line_no"),)),
    Table("rfq", "transaction", "Request for quotation; exactly one per request in the RFQ routes (1:0..1).", ("rfq_id",), (
        ID("rfq_id", "rfq", "RFQ key, assigned in issue order.", unique=True),
        ID("pr_id", "pr", "Request being sourced.", fk="purchase_request.pr_id", unique=True),
        ID("buyer_id", "emp", "Responsible buyer (role BUYER).", fk="requester.requester_id"),
        C("sourcing_type", "TEXT", True, "Competitive (>= 3 quotes) or single source.", enum=("COMPETITIVE", "SINGLE_SOURCE")),
        C("single_source_reason", "TEXT", False, "Required for SINGLE_SOURCE.", enum=("SOLE_SOURCE_OEM", "EMERGENCY")),
        C("currency_code", "TEXT", True, "Currency bids are requested in.", enum=("USD",)),
        C("issued_at", "TIMESTAMP", True, "Issue time.", rule=">= request submitted_at"),
        C("response_due_at", "TIMESTAMP", True, "Bid deadline.", rule="> issued_at"),
        C("min_quotes_required", "INTEGER", True, "3 for competitive, 1 for single source.", enum=(1, 3)),
        C("evaluated_at", "TIMESTAMP", False, "When quotes were evaluated; null while open.", rule=">= response_due_at"),
        C("status", "TEXT", True, "Current lifecycle state.", enum=RFQ_STATUS, derived=True),
        C("cancel_reason", "TEXT", False, "Required when CANCELLED.", enum=("REQUIREMENT_WITHDRAWN", "NO_ELIGIBLE_QUOTES", "AWARDED_SUPPLIER_INACTIVE")),
        C("quotes_received", "INTEGER", True, "Count of supplier_quote rows.", derived=True),
    )),
    Table("rfq_supplier", "bridge", "N:M bridge - suppliers invited to an RFQ and their response.", ("rfq_id", "supplier_id"), (
        ID("rfq_id", "rfq", "RFQ.", fk="rfq.rfq_id"),
        ID("supplier_id", "sup", "Invited supplier (active, serves the category, no open HIGH risk flag).", fk="supplier.supplier_id"),
        C("invited_at", "TIMESTAMP", True, "Invitation time (= RFQ issue)."),
        C("response_status", "TEXT", True, "Response.", enum=("QUOTED", "DECLINED", "NO_RESPONSE", "PENDING")),
        C("responded_at", "TIMESTAMP", False, "Response time for QUOTED / DECLINED."),
    )),
    Table("supplier_quote", "transaction", "Supplier quote header (one per invited supplier that bid).", ("quote_id",), (
        ID("quote_id", "quo", "QUO-<supplier-code>-2026-nnnnnn; global counter in submission order.", unique=True),
        ID("rfq_id", "rfq", "RFQ answered.", fk="rfq.rfq_id"),
        ID("supplier_id", "sup", "Bidding supplier (must be invited).", fk="supplier.supplier_id"),
        C("submitted_at", "TIMESTAMP", True, "Submission time.", rule="issued_at <= x <= response_due_at"),
        C("valid_until", "DATE", True, "Last date the price is valid.", rule=">= submitted date"),
        C("currency_code", "TEXT", True, "Currency the quote is priced in.", enum=CURRENCIES),
        C("incoterm", "TEXT", True, "Delivery term; DDP includes freight and duty in price.", enum=INCOTERMS),
        C("lead_time_days", "INTEGER", True, "Promised lead time from PO.", unit="days", rule="> 0"),
        C("goods_amount", MONEY, True, "Sum of quote lines.", unit="quote currency", derived=True),
        C("freight_amount", MONEY, True, "Freight charge.", unit="quote currency", rule=">= 0"),
        C("total_amount", MONEY, True, "goods_amount + freight_amount.", unit="quote currency", derived=True),
        C("status", "TEXT", True, "Current lifecycle state.", enum=QUOTE_STATUS, derived=True),
    ), unique=(("rfq_id", "supplier_id"),)),
    Table("quote_line", "transaction", "Quoted price per request line.", ("quote_line_id",), (
        ID("quote_line_id", "quol", "<quote_id>-Lnn.", unique=True),
        ID("quote_id", "quo", "Parent quote.", fk="supplier_quote.quote_id"),
        ID("pr_line_id", "prl", "Request line priced (belongs to the RFQ request).", fk="request_line.pr_line_id"),
        C("line_no", "INTEGER", True, "Line number.", rule=">= 1"),
        C("quantity", "INTEGER", True, "Quoted quantity (= request quantity).", rule="> 0"),
        C("unit_price", MONEY, True, "Unit price in quote currency.", rule="> 0"),
        C("line_amount", MONEY, True, "quantity x unit_price.", derived=True),
    ), unique=(("quote_id", "pr_line_id"),)),
    Table("quote_evaluation", "derived", "Buyer comparison record per quote: landed cost, delivery and eligibility (1:1 with evaluated quotes).", ("quote_id",), (
        ID("quote_id", "quo", "Quote evaluated.", fk="supplier_quote.quote_id", unique=True),
        ID("rfq_id", "rfq", "RFQ.", fk="rfq.rfq_id"),
        C("evaluated_at", "TIMESTAMP", True, "Evaluation time (= rfq.evaluated_at)."),
        C("fx_rate_used", RATE, True, "USD per unit used for conversion (fx_rate of the quote month).", unit="USD per unit"),
        C("goods_usd", MONEY, True, "goods_amount x fx_rate_used.", unit="USD", derived=True),
        C("freight_usd", MONEY, True, "freight_amount x fx_rate_used.", unit="USD", derived=True),
        C("duty_usd", MONEY, True, "goods_usd x import_duty_rate when supplier is non-US and incoterm != DDP.", unit="USD", derived=True),
        C("landed_cost_usd", MONEY, True, "goods_usd + freight_usd + duty_usd.", unit="USD", derived=True),
        C("expected_delivery_date", "DATE", True, "evaluation date + 2 business days + lead_time_days.", derived=True),
        C("meets_need_by", "BOOLEAN", True, "expected_delivery_date <= request need_by_date.", derived=True),
        C("is_valid_at_evaluation", "BOOLEAN", True, "valid_until >= evaluation date.", derived=True),
        C("supplier_status_at_evaluation", "TEXT", True, "From supplier_status_history.", enum=SUPPLIER_STATUS, derived=True),
        C("supplier_risk_at_evaluation", "TEXT", True, "Highest open risk flag severity.", enum=RISK_LEVELS, derived=True),
        C("is_eligible", "BOOLEAN", True, "Valid AND supplier ACTIVE AND risk != HIGH.", derived=True),
        C("disqualification_reason", "TEXT", False, "Why ineligible.", enum=("EXPIRED", "SUPPLIER_INACTIVE", "SUPPLIER_HIGH_RISK")),
        C("landed_cost_rank", "INTEGER", False, "Rank among eligible quotes (1 = cheapest).", derived=True),
    )),
    Table("rfq_award", "transaction", "Award recommendation (decision record) for an RFQ (1:0..1).", ("rfq_id",), (
        ID("rfq_id", "rfq", "RFQ.", fk="rfq.rfq_id", unique=True),
        ID("quote_id", "quo", "Selected quote.", fk="supplier_quote.quote_id", unique=True),
        ID("supplier_id", "sup", "Selected supplier (= quote supplier).", fk="supplier.supplier_id"),
        ID("buyer_id", "emp", "Buyer recommending the award.", fk="requester.requester_id"),
        C("recommended_at", "TIMESTAMP", True, "Decision time (= rfq.evaluated_at)."),
        C("award_basis", "TEXT", False, "Rule AWD-1..4 that justified the selection.", enum=AWARD_BASIS),
        C("award_rationale", "TEXT", False, "Mandatory narrative when the selection is not the lowest landed cost."),
        C("awarded_landed_cost_usd", MONEY, True, "Landed cost of the selected quote as evaluated.", unit="USD"),
        C("status", "TEXT", True, "Approval outcome of the award.", enum=("PENDING_APPROVAL", "APPROVED", "REJECTED", "WITHDRAWN"), derived=True),
        C("decided_at", "TIMESTAMP", False, "When the approval chain finished.", derived=True),
    )),
    Table("approval", "event", "One row per approval step requested. Steps are sequential; history is never overwritten.", ("approval_id",), (
        ID("approval_id", "apr", "Approval step key, assigned in request order.", unique=True),
        ID("pr_id", "pr", "Request being approved.", fk="purchase_request.pr_id"),
        ID("rfq_id", "rfq", "Set when approving an RFQ award.", req=False, fk="rfq.rfq_id"),
        C("approval_type", "TEXT", True, "SPEND = threshold chain; others are exception approvals.", enum=APPROVAL_TYPES),
        C("approval_level", "TEXT", True, "Authority level required by the rule.", enum=APPROVAL_LEVELS),
        C("step_no", "INTEGER", True, "Order within the chain.", rule=">= 1"),
        ID("approver_id", "emp", "Resolved approver (never the requester).", fk="requester.requester_id"),
        C("basis_amount_usd", MONEY, True, "Amount under approval.", unit="USD"),
        C("rule_id", "TEXT", True, "Rule that required the step (APR-T1..T4, BUD-EXC, SRC-SS, SRC-WAIVER)."),
        C("requested_at", "TIMESTAMP", True, "When the step was routed."),
        C("decided_at", "TIMESTAMP", False, "Decision time; null while PENDING.", rule=">= requested_at"),
        C("decision", "TEXT", True, "Outcome.", enum=DECISIONS),
        C("decision_reason", "TEXT", False, "Reason code (required unless PENDING).", enum=DECISION_REASONS),
        C("comment", "TEXT", False, "Approver comment."),
    ), unique=(("pr_id", "rfq_id", "approval_type", "approval_level", "step_no"),)),
    Table("purchase_order", "transaction", "Purchase order header. RFQ POs copy the awarded quote; direct POs use contract pricing.", ("po_id",), (
        ID("po_id", "po", "PO key, assigned in issue order.", unique=True),
        ID("supplier_id", "sup", "Supplier ordered from.", fk="supplier.supplier_id"),
        ID("department_id", "dept", "Ordering department.", fk="department.department_id"),
        ID("budget_id", "bud", "Budget committed.", fk="budget.budget_id"),
        ID("buyer_id", "emp", "Buyer who issued the PO.", fk="requester.requester_id"),
        C("source_type", "TEXT", True, "RFQ_AWARD (1 PO per awarded RFQ) or DIRECT_CONTRACT (may consolidate requests).", enum=("RFQ_AWARD", "DIRECT_CONTRACT")),
        ID("rfq_id", "rfq", "RFQ for RFQ_AWARD POs.", req=False, fk="rfq.rfq_id"),
        ID("quote_id", "quo", "Awarded quote for RFQ_AWARD POs.", req=False, fk="supplier_quote.quote_id"),
        C("issued_at", "TIMESTAMP", True, "Issue time."),
        C("currency_code", "TEXT", True, "PO currency (must equal the awarded quote currency).", enum=CURRENCIES),
        C("payment_terms", "TEXT", True, "Payment terms.", enum=("NET30", "NET45", "NET60")),
        C("incoterm", "TEXT", True, "Delivery term.", enum=INCOTERMS),
        C("promised_date", "DATE", True, "issue date + lead time.", derived=True),
        C("goods_amount", MONEY, True, "Sum of PO lines.", unit="PO currency", derived=True),
        C("freight_amount", MONEY, True, "Freight (from quote; 0 for direct).", unit="PO currency"),
        C("total_amount", MONEY, True, "goods_amount + freight_amount.", unit="PO currency", derived=True),
        C("fx_rate_to_usd", RATE, True, "fx_rate of the issue month.", unit="USD per unit"),
        C("est_duty_usd", MONEY, True, "Estimated import duty.", unit="USD", derived=True),
        C("total_usd", MONEY, True, "total_amount x fx_rate_to_usd + est_duty_usd; the budget commitment.", unit="USD", derived=True),
        C("status", "TEXT", True, "Current lifecycle state.", enum=PO_STATUS, derived=True),
        C("closed_at", "TIMESTAMP", False, "When fully received or short-closed.", derived=True),
    )),
    Table("po_line", "transaction", "PO line; also the bridge between POs and request lines (PR:PO is N:M).", ("po_line_id",), (
        ID("po_line_id", "pol", "<po_id>-Lnn.", unique=True),
        ID("po_id", "po", "Parent PO.", fk="purchase_order.po_id"),
        C("line_no", "INTEGER", True, "Line number.", rule=">= 1"),
        ID("pr_id", "pr", "Request the line fulfils.", fk="purchase_request.pr_id"),
        ID("pr_line_id", "prl", "Request line fulfilled.", fk="request_line.pr_line_id", unique=True),
        ID("quote_line_id", "quol", "Awarded quote line (RFQ POs).", req=False, fk="quote_line.quote_line_id"),
        ID("item_id", "item", "Item.", fk="item.item_id"),
        C("quantity", "INTEGER", True, "Ordered quantity.", rule="> 0"),
        C("unit_price", MONEY, True, "Unit price in PO currency.", rule="> 0"),
        C("line_amount", MONEY, True, "quantity x unit_price.", derived=True),
        C("qty_received", "INTEGER", True, "Sum of accepted delivery quantities.", derived=True),
        C("line_status", "TEXT", True, "Receipt state.", enum=("OPEN", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED_SHORT"), derived=True),
    ), unique=(("po_id", "line_no"),)),
    Table("delivery", "event", "Goods receipt / service acceptance event. Several per PO for partial deliveries.", ("delivery_id",), (
        ID("delivery_id", "del", "DEL-<po_id>-nn, numbered per PO in arrival order.", unique=True),
        ID("po_id", "po", "PO delivered against.", fk="purchase_order.po_id"),
        C("delivery_seq", "INTEGER", True, "Sequence within the PO.", rule=">= 1"),
        C("carrier", "TEXT", True, "Carrier (synthetic)."),
        C("delivered_at", "TIMESTAMP", True, "Receipt time.", rule=">= po issued_at"),
        ID("received_by", "emp", "Employee who receipted.", fk="requester.requester_id"),
        C("is_on_time", "BOOLEAN", True, "delivered date <= PO promised_date.", derived=True),
        C("days_late", "INTEGER", True, "max(0, delivered date - promised_date).", unit="days", derived=True),
        C("completes_po", "BOOLEAN", True, "PO fully received after this delivery.", derived=True),
    ), unique=(("po_id", "delivery_seq"),)),
    Table("delivery_line", "event", "Quantities delivered, accepted and rejected per PO line.", ("delivery_line_id",), (
        ID("delivery_line_id", "dell", "<delivery_id>-Lnn.", unique=True),
        ID("delivery_id", "del", "Parent delivery.", fk="delivery.delivery_id"),
        ID("po_line_id", "pol", "PO line.", fk="po_line.po_line_id"),
        C("qty_delivered", "INTEGER", True, "Delivered quantity.", rule="> 0"),
        C("qty_accepted", "INTEGER", True, "Accepted quantity.", rule="qty_accepted + qty_rejected = qty_delivered"),
        C("qty_rejected", "INTEGER", True, "Rejected at inspection.", rule=">= 0"),
        C("rejection_reason", "TEXT", False, "Required when qty_rejected > 0.", enum=("DAMAGED", "QUALITY_FAIL", "WRONG_ITEM")),
    )),
    Table("budget_transaction", "event", "Append-only budget ledger; balances are sums of deltas.", ("budget_txn_id",), (
        ID("budget_txn_id", "btx", "Ledger key in time order.", unique=True),
        ID("budget_id", "bud", "Budget affected.", fk="budget.budget_id"),
        C("txn_ts", "TIMESTAMP", True, "Posting time."),
        C("txn_type", "TEXT", True, "Ledger movement.", enum=("RESERVE", "RESERVE_ADJUST", "RELEASE", "COMMIT", "DECOMMIT", "TRANSFER_IN", "TRANSFER_OUT")),
        C("source_type", "TEXT", True, "Document that caused the posting.", enum=("PURCHASE_REQUEST", "PURCHASE_ORDER", "APPROVAL")),
        C("source_id", "TEXT", True, "Polymorphic reference: pr_id, po_id or approval_id per source_type."),
        C("allocated_delta_usd", MONEY, True, "Change to allocation (transfers).", unit="USD"),
        C("reserved_delta_usd", MONEY, True, "Change to reserved (pre-encumbrance).", unit="USD"),
        C("committed_delta_usd", MONEY, True, "Change to committed (PO encumbrance).", unit="USD"),
        C("note", "TEXT", False, "Narrative."),
    )),
    Table("budget_balance", "derived", "Snapshot balances recomputed from budget + budget_transaction.", ("budget_id",), (
        ID("budget_id", "bud", "Budget.", fk="budget.budget_id", unique=True),
        C("allocated_original_usd", MONEY, True, "budget.allocated_amount_usd.", unit="USD", derived=True),
        C("transfers_net_usd", MONEY, True, "Sum of allocated_delta_usd.", unit="USD", derived=True),
        C("allocated_current_usd", MONEY, True, "Original + transfers.", unit="USD", derived=True),
        C("reserved_usd", MONEY, True, "Sum of reserved_delta_usd.", unit="USD", derived=True),
        C("committed_usd", MONEY, True, "Sum of committed_delta_usd.", unit="USD", derived=True),
        C("available_usd", MONEY, True, "allocated_current - reserved - committed.", unit="USD", derived=True),
        C("utilization_pct", PCT, True, "(reserved + committed) / allocated_current.", unit="fraction", derived=True),
    )),
    Table("status_event", "event", "Lifecycle history for requests, RFQs, quotes and POs (append-only).", ("event_id",), (
        ID("event_id", "evt", "Event key in time order.", unique=True),
        C("entity_type", "TEXT", True, "Entity whose state changed.", enum=EVENT_ENTITIES),
        C("entity_id", "TEXT", True, "Polymorphic reference to the entity key."),
        C("from_status", "TEXT", False, "Previous state; null for creation."),
        C("to_status", "TEXT", True, "New state."),
        C("event_ts", "TIMESTAMP", True, "Transition time."),
        ID("actor_id", "emp", "Employee who caused the change; null for supplier/system events.", req=False, fk="requester.requester_id"),
        C("reason", "TEXT", False, "Reason / reference."),
    )),
    Table("exception_register", "derived", "Documented business exceptions with reason and audit references (not anomaly labels).", ("exception_id",), (
        ID("exception_id", "exc", "Exception key.", unique=True),
        C("exception_type", "TEXT", True, "Exception class.", enum=EXCEPTION_TYPES),
        C("entity_type", "TEXT", True, "Entity the exception is about.", enum=("PURCHASE_REQUEST", "RFQ", "SUPPLIER_QUOTE", "PURCHASE_ORDER", "DELIVERY")),
        C("entity_id", "TEXT", True, "Polymorphic reference."),
        ID("pr_id", "pr", "Related request.", req=False, fk="purchase_request.pr_id"),
        C("raised_at", "TIMESTAMP", True, "When raised."),
        C("reason_code", "TEXT", True, "Machine-readable reason."),
        C("reason_text", "TEXT", True, "Human-readable reason."),
        ID("approval_id", "apr", "Approval that authorised it, when one is required.", req=False, fk="approval.approval_id"),
        C("resolution", "TEXT", True, "Outcome.", enum=("APPROVED", "REJECTED", "PENDING", "WITHDRAWN", "EXCLUDED", "RECORDED")),
        C("resolved_at", "TIMESTAMP", False, "When resolved."),
    )),
)

TABLE_BY_NAME = {t.name: t for t in TABLES}
TABLE_ORDER = [t.name for t in TABLES]   # parents before children (safe insert order)

GROUND_TRUTH_COLUMNS = (
    ("gt_id", "Label key GT-nnnnn."),
    ("issue_type", "Anomaly class (one of the 7 required edge cases or SPLIT_PURCHASE)."),
    ("sub_type", "Variant of the anomaly."),
    ("severity", "HIGH / MEDIUM / LOW."),
    ("entity_type", "Primary entity labelled."),
    ("entity_id", "Primary entity key."),
    ("related_ids", "Pipe-separated keys of related records."),
    ("control_rule", "Control that is violated."),
    ("expected_handling", "What the process should have done."),
    ("description", "Narrative."),
    ("evidence", "JSON with the values that prove the anomaly."),
)


def columns(table: str) -> list[str]:
    return [c.name for c in TABLE_BY_NAME[table].cols]
