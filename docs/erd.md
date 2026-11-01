# Entity-relationship model and lifecycles

GitHub renders the diagrams below. The full column list, cardinality table and validation rules
are in [data_dictionary.md](data_dictionary.md).

## Entity-relationship diagram

```mermaid
erDiagram
    DEPARTMENT ||--o{ REQUESTER : employs
    REQUESTER |o--o{ REQUESTER : "manages (manager_id)"
    DEPARTMENT ||--o{ BUDGET : owns
    REQUESTER ||--o{ BUDGET : "owns (owner_id)"
    BUDGET ||--o{ BUDGET_TRANSACTION : "ledger postings"
    BUDGET ||--|| BUDGET_BALANCE : "derived snapshot"

    ITEM_CATEGORY ||--o{ ITEM : classifies
    SUPPLIER ||--o{ SUPPLIER_CATEGORY : serves
    ITEM_CATEGORY ||--o{ SUPPLIER_CATEGORY : "served by"
    SUPPLIER ||--o{ SUPPLIER_STATUS_HISTORY : "effective-dated status"
    SUPPLIER ||--o{ SUPPLIER_RISK_FLAG : "risk signals"
    SUPPLIER |o--o{ ITEM : "OEM for sole-source items"

    REQUESTER ||--o{ PURCHASE_REQUEST : raises
    DEPARTMENT ||--o{ PURCHASE_REQUEST : "charged to"
    BUDGET ||--o{ PURCHASE_REQUEST : funds
    PURCHASE_REQUEST ||--|{ REQUEST_LINE : contains
    ITEM ||--o{ REQUEST_LINE : "requested as"

    PURCHASE_REQUEST ||--o| RFQ : "sourced by (RFQ routes)"
    RFQ ||--|{ RFQ_SUPPLIER : invites
    SUPPLIER ||--o{ RFQ_SUPPLIER : "invited to"
    RFQ ||--o{ SUPPLIER_QUOTE : receives
    SUPPLIER ||--o{ SUPPLIER_QUOTE : submits
    SUPPLIER_QUOTE ||--|{ QUOTE_LINE : prices
    REQUEST_LINE ||--o{ QUOTE_LINE : "priced by"
    SUPPLIER_QUOTE ||--o| QUOTE_EVALUATION : "evaluated as"
    RFQ ||--o| RFQ_AWARD : "decided by"
    SUPPLIER_QUOTE ||--o| RFQ_AWARD : "selected in"

    PURCHASE_REQUEST ||--o{ APPROVAL : "approved through"
    RFQ |o--o{ APPROVAL : "award approved through"
    REQUESTER ||--o{ APPROVAL : decides

    SUPPLIER ||--o{ PURCHASE_ORDER : "ordered from"
    RFQ |o--o| PURCHASE_ORDER : "awarded into"
    SUPPLIER_QUOTE |o--o| PURCHASE_ORDER : "copied into"
    PURCHASE_ORDER ||--|{ PO_LINE : contains
    REQUEST_LINE ||--o| PO_LINE : "fulfilled by"
    QUOTE_LINE |o--o| PO_LINE : "priced from"
    PURCHASE_ORDER ||--o{ DELIVERY : "received in"
    DELIVERY ||--|{ DELIVERY_LINE : contains
    PO_LINE ||--o{ DELIVERY_LINE : "received as"

    PURCHASE_REQUEST ||--o{ STATUS_EVENT : "history (polymorphic)"
    PURCHASE_REQUEST ||--o{ EXCEPTION_REGISTER : "documented exceptions"
```

### Many-to-many relationships and their bridges

| Relationship | Bridge | Notes |
|---|---|---|
| Supplier <-> Category | `supplier_category` | Carries the contract preference rank and discount |
| RFQ <-> Supplier | `rfq_supplier` | Invitation and response status; every quote must have an invitation row |
| Purchase request <-> Purchase order | `po_line` | One row per ordered request line. Direct-buy POs consolidate several requests; each request line is ordered at most once (`po_line.pr_line_id` is unique). |

### Polymorphic references

`budget_transaction.source_id` (by `source_type`), `status_event.entity_id` (by `entity_type`) and
`exception_register.entity_id` (by `entity_type`) point at different tables. SQL cannot enforce
these, so `validate.py` resolves every one of them.

## Lifecycle state machines

`status_event` stores every transition, and each entity's `status` column equals its last event.
The validator checks chain continuity (`from_status` = previous `to_status`, times non-decreasing).
`controls.py` checks the whitelists below. The only transitions outside them are the labelled
`PO_WITHOUT_APPROVAL` cases (`PENDING_APPROVAL -> ORDERED`).

### Purchase request

```mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> PENDING_APPROVAL: direct buy (budget check + chain)
    SUBMITTED --> SOURCING: RFQ issued
    SUBMITTED --> CANCELLED
    SOURCING --> PENDING_APPROVAL: award recommended
    SOURCING --> CANCELLED: withdrawn / no eligible quotes
    PENDING_APPROVAL --> APPROVED
    PENDING_APPROVAL --> REJECTED
    PENDING_APPROVAL --> CANCELLED
    APPROVED --> ORDERED: PO issued
    APPROVED --> CANCELLED: withdrawn before PO run / supplier inactive
    ORDERED --> PARTIALLY_RECEIVED
    ORDERED --> RECEIVED
    PARTIALLY_RECEIVED --> RECEIVED
    PARTIALLY_RECEIVED --> CLOSED_SHORT
```

### RFQ

```mermaid
stateDiagram-v2
    [*] --> OPEN
    OPEN --> UNDER_EVALUATION: bid deadline
    OPEN --> CANCELLED: requirement withdrawn
    UNDER_EVALUATION --> AWARD_RECOMMENDED: rules AWD-1..4
    UNDER_EVALUATION --> CANCELLED: no eligible quotes
    AWARD_RECOMMENDED --> AWARDED: approval chain complete
    AWARD_RECOMMENDED --> AWARD_REJECTED
    AWARDED --> CANCELLED: awarded supplier inactive before PO
```

### Supplier quote and purchase order

```mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> SELECTED
    RECEIVED --> NOT_SELECTED
    RECEIVED --> DISQUALIFIED: expired / inactive / high risk
    RECEIVED --> CANCELLED
    SELECTED --> AWARDED
    SELECTED --> AWARD_REJECTED
    AWARDED --> CANCELLED
```

```mermaid
stateDiagram-v2
    [*] --> ISSUED
    ISSUED --> PARTIALLY_RECEIVED
    ISSUED --> RECEIVED
    PARTIALLY_RECEIVED --> RECEIVED
    PARTIALLY_RECEIVED --> CLOSED_SHORT: balance cancelled, commitment released
```

Supplier status (`ACTIVE`, `SUSPENDED`, `INACTIVE`) and risk flags are effective-dated: each row
has an interval, and every decision (invitation, evaluation, PO) is checked against the status
on its own date.

## Effective-dated records

| Table | Validity columns | Used for |
|---|---|---|
| `supplier_status_history` | `effective_from`, `effective_to` (half-open; null = current) | Supplier must be `ACTIVE` on the invitation, evaluation and PO dates |
| `supplier_risk_flag` | `raised_date`, `cleared_date` (null = open) | An open HIGH flag blocks invitation and award; MEDIUM can trigger AWD-3; delivery and quality flags worsen performance |
| `requester` | `hire_date`, `termination_date` | Requester must be employed on the submission date; deliveries are received by the requester only while employed |
| `budget` | `effective_from`, `effective_to` | FY2026 budget period |
| `supplier_category` | `effective_from` | Date the supplier was approved for the category |
| `department` | `effective_from` | Date the department record became effective |
| `fx_rate` | `rate_month` | Quote month rate at evaluation; issue month rate on the PO |

`supplier.status` and `supplier.risk_rating` are snapshot values derived from the history tables
at `AS_OF`. Decisions never use them.
