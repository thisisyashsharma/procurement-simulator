-- Procurement P2P synthetic dataset: schema (SQLite / PostgreSQL compatible)

CREATE TABLE department (
  department_id TEXT NOT NULL,
  department_name TEXT NOT NULL,
  cost_center TEXT NOT NULL,
  division TEXT NOT NULL,
  status TEXT NOT NULL,
  effective_from DATE NOT NULL,
  PRIMARY KEY (department_id),
  CHECK (division IS NULL OR division IN ('CORPORATE', 'TECHNOLOGY', 'OPERATIONS', 'COMMERCIAL')),
  CHECK (status IS NULL OR status IN ('ACTIVE', 'INACTIVE'))
);

CREATE TABLE requester (
  requester_id TEXT NOT NULL,
  full_name TEXT NOT NULL,
  email TEXT NOT NULL,
  department_id TEXT NOT NULL,
  job_title TEXT NOT NULL,
  role TEXT NOT NULL,
  approval_limit_usd NUMERIC(14,2),
  manager_id TEXT,
  hire_date DATE NOT NULL,
  termination_date DATE,
  status TEXT NOT NULL,
  PRIMARY KEY (requester_id),
  FOREIGN KEY (department_id) REFERENCES department (department_id),
  FOREIGN KEY (manager_id) REFERENCES requester (requester_id),
  CHECK (role IS NULL OR role IN ('CEO', 'CFO', 'VP', 'DIRECTOR', 'MANAGER', 'STAFF', 'BUYER', 'FINANCE_CONTROLLER')),
  CHECK (status IS NULL OR status IN ('ACTIVE', 'INACTIVE'))
);

CREATE TABLE item_category (
  category_code TEXT NOT NULL,
  category_name TEXT NOT NULL,
  budget_type TEXT NOT NULL,
  is_service BOOLEAN NOT NULL,
  import_duty_rate NUMERIC(6,4) NOT NULL,
  standard_lead_time_days INTEGER NOT NULL,
  PRIMARY KEY (category_code),
  CHECK (budget_type IS NULL OR budget_type IN ('OPEX', 'CAPEX'))
);

CREATE TABLE supplier (
  supplier_id TEXT NOT NULL,
  supplier_name TEXT NOT NULL,
  country_code TEXT NOT NULL,
  currency_code TEXT NOT NULL,
  supplier_tier TEXT NOT NULL,
  payment_terms TEXT NOT NULL,
  default_incoterm TEXT NOT NULL,
  onboarded_date DATE NOT NULL,
  status TEXT NOT NULL,
  risk_rating TEXT NOT NULL,
  contact_email TEXT NOT NULL,
  PRIMARY KEY (supplier_id),
  CHECK (country_code IS NULL OR country_code IN ('US', 'CA', 'MX', 'DE', 'GB', 'IN', 'CN')),
  CHECK (currency_code IS NULL OR currency_code IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'INR', 'CNY')),
  CHECK (supplier_tier IS NULL OR supplier_tier IN ('STRATEGIC', 'PREFERRED', 'APPROVED')),
  CHECK (payment_terms IS NULL OR payment_terms IN ('NET30', 'NET45', 'NET60')),
  CHECK (default_incoterm IS NULL OR default_incoterm IN ('DDP', 'DAP', 'FCA', 'FOB', 'EXW')),
  CHECK (status IS NULL OR status IN ('ACTIVE', 'SUSPENDED', 'INACTIVE')),
  CHECK (risk_rating IS NULL OR risk_rating IN ('NONE', 'LOW', 'MEDIUM', 'HIGH'))
);

CREATE TABLE item (
  item_id TEXT NOT NULL,
  item_name TEXT NOT NULL,
  category_code TEXT NOT NULL,
  uom TEXT NOT NULL,
  list_price_usd NUMERIC(14,2) NOT NULL,
  is_sole_source BOOLEAN NOT NULL,
  sole_source_supplier_id TEXT,
  PRIMARY KEY (item_id),
  FOREIGN KEY (category_code) REFERENCES item_category (category_code),
  FOREIGN KEY (sole_source_supplier_id) REFERENCES supplier (supplier_id),
  CHECK (uom IS NULL OR uom IN ('EA', 'BOX', 'PK', 'KG', 'ROLL', 'LIC', 'HR'))
);

CREATE TABLE supplier_category (
  supplier_id TEXT NOT NULL,
  category_code TEXT NOT NULL,
  preference_rank INTEGER,
  contract_discount_pct NUMERIC(6,4),
  effective_from DATE NOT NULL,
  PRIMARY KEY (supplier_id, category_code),
  FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
  FOREIGN KEY (category_code) REFERENCES item_category (category_code),
  CHECK (preference_rank IS NULL OR preference_rank IN (1, 2))
);

CREATE TABLE supplier_status_history (
  status_history_id TEXT NOT NULL,
  supplier_id TEXT NOT NULL,
  status TEXT NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE,
  reason_code TEXT NOT NULL,
  PRIMARY KEY (status_history_id),
  FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
  UNIQUE (supplier_id, effective_from),
  CHECK (status IS NULL OR status IN ('ACTIVE', 'SUSPENDED', 'INACTIVE')),
  CHECK (reason_code IS NULL OR reason_code IN ('ONBOARDED', 'CONTRACT_TERMINATED', 'MERGED_ACQUIRED', 'COMPLIANCE_REVIEW', 'COMPLIANCE_FAILURE', 'VOLUNTARY_EXIT', 'REINSTATED'))
);

CREATE TABLE supplier_risk_flag (
  risk_flag_id TEXT NOT NULL,
  supplier_id TEXT NOT NULL,
  flag_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  raised_date DATE NOT NULL,
  cleared_date DATE,
  source TEXT NOT NULL,
  PRIMARY KEY (risk_flag_id),
  FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
  CHECK (flag_type IS NULL OR flag_type IN ('FINANCIAL_DISTRESS', 'SANCTIONS_SCREENING_HIT', 'QUALITY_ISSUE', 'DELIVERY_PERFORMANCE', 'CYBER_INCIDENT', 'ESG_CONCERN')),
  CHECK (severity IS NULL OR severity IN ('LOW', 'MEDIUM', 'HIGH')),
  CHECK (source IS NULL OR source IN ('CREDIT_MONITORING', 'SANCTIONS_SCREENING', 'QUALITY_AUDIT', 'SUPPLIER_SCORECARD', 'NEWS_MONITORING'))
);

CREATE TABLE fx_rate (
  currency_code TEXT NOT NULL,
  rate_month TEXT NOT NULL,
  usd_per_unit NUMERIC(12,6) NOT NULL,
  PRIMARY KEY (currency_code, rate_month),
  CHECK (currency_code IS NULL OR currency_code IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'INR', 'CNY'))
);

CREATE TABLE budget (
  budget_id TEXT NOT NULL,
  department_id TEXT NOT NULL,
  fiscal_year INTEGER NOT NULL,
  budget_type TEXT NOT NULL,
  allocated_amount_usd NUMERIC(14,2) NOT NULL,
  owner_id TEXT NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (budget_id),
  FOREIGN KEY (department_id) REFERENCES department (department_id),
  FOREIGN KEY (owner_id) REFERENCES requester (requester_id),
  UNIQUE (department_id, fiscal_year, budget_type),
  CHECK (fiscal_year IS NULL OR fiscal_year IN (2026)),
  CHECK (budget_type IS NULL OR budget_type IN ('OPEX', 'CAPEX', 'CONTINGENCY')),
  CHECK (status IS NULL OR status IN ('OPEN', 'CLOSED'))
);

CREATE TABLE purchase_request (
  pr_id TEXT NOT NULL,
  requester_id TEXT NOT NULL,
  department_id TEXT NOT NULL,
  budget_id TEXT NOT NULL,
  category_code TEXT NOT NULL,
  submitted_at TIMESTAMP NOT NULL,
  need_by_date DATE NOT NULL,
  priority TEXT NOT NULL,
  justification TEXT,
  sourcing_route TEXT NOT NULL,
  estimated_total_usd NUMERIC(14,2) NOT NULL,
  budget_checked_at TIMESTAMP,
  budget_available_usd NUMERIC(14,2),
  budget_check_result TEXT,
  approval_basis_usd NUMERIC(14,2),
  approval_tier INTEGER,
  status TEXT NOT NULL,
  status_updated_at TIMESTAMP NOT NULL,
  PRIMARY KEY (pr_id),
  FOREIGN KEY (requester_id) REFERENCES requester (requester_id),
  FOREIGN KEY (department_id) REFERENCES department (department_id),
  FOREIGN KEY (budget_id) REFERENCES budget (budget_id),
  FOREIGN KEY (category_code) REFERENCES item_category (category_code),
  CHECK (priority IS NULL OR priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
  CHECK (sourcing_route IS NULL OR sourcing_route IN ('DIRECT', 'COMPETITIVE_RFQ', 'SINGLE_SOURCE_RFQ')),
  CHECK (budget_check_result IS NULL OR budget_check_result IN ('WITHIN_BUDGET', 'OVER_BUDGET')),
  CHECK (approval_tier IS NULL OR approval_tier IN (1, 2, 3, 4)),
  CHECK (status IS NULL OR status IN ('SUBMITTED', 'SOURCING', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'CANCELLED', 'ORDERED', 'PARTIALLY_RECEIVED', 'RECEIVED', 'CLOSED_SHORT'))
);

CREATE TABLE request_line (
  pr_line_id TEXT NOT NULL,
  pr_id TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  item_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  uom TEXT NOT NULL,
  est_unit_price_usd NUMERIC(14,2) NOT NULL,
  est_line_total_usd NUMERIC(14,2) NOT NULL,
  PRIMARY KEY (pr_line_id),
  FOREIGN KEY (pr_id) REFERENCES purchase_request (pr_id),
  FOREIGN KEY (item_id) REFERENCES item (item_id),
  UNIQUE (pr_id, line_no),
  CHECK (uom IS NULL OR uom IN ('EA', 'BOX', 'PK', 'KG', 'ROLL', 'LIC', 'HR'))
);

CREATE TABLE rfq (
  rfq_id TEXT NOT NULL,
  pr_id TEXT NOT NULL,
  buyer_id TEXT NOT NULL,
  sourcing_type TEXT NOT NULL,
  single_source_reason TEXT,
  currency_code TEXT NOT NULL,
  issued_at TIMESTAMP NOT NULL,
  response_due_at TIMESTAMP NOT NULL,
  min_quotes_required INTEGER NOT NULL,
  evaluated_at TIMESTAMP,
  status TEXT NOT NULL,
  cancel_reason TEXT,
  quotes_received INTEGER NOT NULL,
  PRIMARY KEY (rfq_id),
  FOREIGN KEY (pr_id) REFERENCES purchase_request (pr_id),
  FOREIGN KEY (buyer_id) REFERENCES requester (requester_id),
  CHECK (sourcing_type IS NULL OR sourcing_type IN ('COMPETITIVE', 'SINGLE_SOURCE')),
  CHECK (single_source_reason IS NULL OR single_source_reason IN ('SOLE_SOURCE_OEM', 'EMERGENCY')),
  CHECK (currency_code IS NULL OR currency_code IN ('USD')),
  CHECK (min_quotes_required IS NULL OR min_quotes_required IN (1, 3)),
  CHECK (status IS NULL OR status IN ('OPEN', 'UNDER_EVALUATION', 'AWARD_RECOMMENDED', 'AWARDED', 'AWARD_REJECTED', 'CANCELLED')),
  CHECK (cancel_reason IS NULL OR cancel_reason IN ('REQUIREMENT_WITHDRAWN', 'NO_ELIGIBLE_QUOTES', 'AWARDED_SUPPLIER_INACTIVE'))
);

CREATE TABLE rfq_supplier (
  rfq_id TEXT NOT NULL,
  supplier_id TEXT NOT NULL,
  invited_at TIMESTAMP NOT NULL,
  response_status TEXT NOT NULL,
  responded_at TIMESTAMP,
  PRIMARY KEY (rfq_id, supplier_id),
  FOREIGN KEY (rfq_id) REFERENCES rfq (rfq_id),
  FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
  CHECK (response_status IS NULL OR response_status IN ('QUOTED', 'DECLINED', 'NO_RESPONSE', 'PENDING'))
);

CREATE TABLE supplier_quote (
  quote_id TEXT NOT NULL,
  rfq_id TEXT NOT NULL,
  supplier_id TEXT NOT NULL,
  submitted_at TIMESTAMP NOT NULL,
  valid_until DATE NOT NULL,
  currency_code TEXT NOT NULL,
  incoterm TEXT NOT NULL,
  lead_time_days INTEGER NOT NULL,
  goods_amount NUMERIC(14,2) NOT NULL,
  freight_amount NUMERIC(14,2) NOT NULL,
  total_amount NUMERIC(14,2) NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (quote_id),
  FOREIGN KEY (rfq_id) REFERENCES rfq (rfq_id),
  FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
  UNIQUE (rfq_id, supplier_id),
  CHECK (currency_code IS NULL OR currency_code IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'INR', 'CNY')),
  CHECK (incoterm IS NULL OR incoterm IN ('DDP', 'DAP', 'FCA', 'FOB', 'EXW')),
  CHECK (status IS NULL OR status IN ('RECEIVED', 'SELECTED', 'NOT_SELECTED', 'DISQUALIFIED', 'AWARDED', 'AWARD_REJECTED', 'CANCELLED'))
);

CREATE TABLE quote_line (
  quote_line_id TEXT NOT NULL,
  quote_id TEXT NOT NULL,
  pr_line_id TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  quantity INTEGER NOT NULL,
  unit_price NUMERIC(14,2) NOT NULL,
  line_amount NUMERIC(14,2) NOT NULL,
  PRIMARY KEY (quote_line_id),
  FOREIGN KEY (quote_id) REFERENCES supplier_quote (quote_id),
  FOREIGN KEY (pr_line_id) REFERENCES request_line (pr_line_id),
  UNIQUE (quote_id, pr_line_id)
);

CREATE TABLE quote_evaluation (
  quote_id TEXT NOT NULL,
  rfq_id TEXT NOT NULL,
  evaluated_at TIMESTAMP NOT NULL,
  fx_rate_used NUMERIC(12,6) NOT NULL,
  goods_usd NUMERIC(14,2) NOT NULL,
  freight_usd NUMERIC(14,2) NOT NULL,
  duty_usd NUMERIC(14,2) NOT NULL,
  landed_cost_usd NUMERIC(14,2) NOT NULL,
  expected_delivery_date DATE NOT NULL,
  meets_need_by BOOLEAN NOT NULL,
  is_valid_at_evaluation BOOLEAN NOT NULL,
  supplier_status_at_evaluation TEXT NOT NULL,
  supplier_risk_at_evaluation TEXT NOT NULL,
  is_eligible BOOLEAN NOT NULL,
  disqualification_reason TEXT,
  landed_cost_rank INTEGER,
  PRIMARY KEY (quote_id),
  FOREIGN KEY (quote_id) REFERENCES supplier_quote (quote_id),
  FOREIGN KEY (rfq_id) REFERENCES rfq (rfq_id),
  CHECK (supplier_status_at_evaluation IS NULL OR supplier_status_at_evaluation IN ('ACTIVE', 'SUSPENDED', 'INACTIVE')),
  CHECK (supplier_risk_at_evaluation IS NULL OR supplier_risk_at_evaluation IN ('NONE', 'LOW', 'MEDIUM', 'HIGH')),
  CHECK (disqualification_reason IS NULL OR disqualification_reason IN ('EXPIRED', 'SUPPLIER_INACTIVE', 'SUPPLIER_HIGH_RISK'))
);

CREATE TABLE rfq_award (
  rfq_id TEXT NOT NULL,
  quote_id TEXT NOT NULL,
  supplier_id TEXT NOT NULL,
  buyer_id TEXT NOT NULL,
  recommended_at TIMESTAMP NOT NULL,
  award_basis TEXT,
  award_rationale TEXT,
  awarded_landed_cost_usd NUMERIC(14,2) NOT NULL,
  status TEXT NOT NULL,
  decided_at TIMESTAMP,
  PRIMARY KEY (rfq_id),
  FOREIGN KEY (rfq_id) REFERENCES rfq (rfq_id),
  FOREIGN KEY (quote_id) REFERENCES supplier_quote (quote_id),
  FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
  FOREIGN KEY (buyer_id) REFERENCES requester (requester_id),
  CHECK (award_basis IS NULL OR award_basis IN ('LOWEST_LANDED_COST', 'DELIVERY_REQUIREMENT', 'RISK_MITIGATION', 'SOLE_SOURCE')),
  CHECK (status IS NULL OR status IN ('PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'WITHDRAWN'))
);

CREATE TABLE approval (
  approval_id TEXT NOT NULL,
  pr_id TEXT NOT NULL,
  rfq_id TEXT,
  approval_type TEXT NOT NULL,
  approval_level TEXT NOT NULL,
  step_no INTEGER NOT NULL,
  approver_id TEXT NOT NULL,
  basis_amount_usd NUMERIC(14,2) NOT NULL,
  rule_id TEXT NOT NULL,
  requested_at TIMESTAMP NOT NULL,
  decided_at TIMESTAMP,
  decision TEXT NOT NULL,
  decision_reason TEXT,
  comment TEXT,
  PRIMARY KEY (approval_id),
  FOREIGN KEY (pr_id) REFERENCES purchase_request (pr_id),
  FOREIGN KEY (rfq_id) REFERENCES rfq (rfq_id),
  FOREIGN KEY (approver_id) REFERENCES requester (requester_id),
  UNIQUE (pr_id, rfq_id, approval_type, approval_level, step_no),
  CHECK (approval_type IS NULL OR approval_type IN ('SPEND', 'BUDGET_EXCEPTION', 'SINGLE_SOURCE', 'COMPETITION_WAIVER')),
  CHECK (approval_level IS NULL OR approval_level IN ('MANAGER', 'DIRECTOR', 'VP', 'CFO', 'FINANCE_CONTROLLER', 'PROCUREMENT_DIRECTOR')),
  CHECK (decision IS NULL OR decision IN ('PENDING', 'APPROVED', 'REJECTED', 'WITHDRAWN')),
  CHECK (decision_reason IS NULL OR decision_reason IN ('WITHIN_POLICY', 'INSUFFICIENT_JUSTIFICATION', 'BUDGET_EXCEEDED', 'CONTINGENCY_EXHAUSTED', 'LOW_PRIORITY_DEFERRED', 'CFO_DEFERRED', 'JUSTIFICATION_ACCEPTED', 'REQUEST_WITHDRAWN'))
);

CREATE TABLE purchase_order (
  po_id TEXT NOT NULL,
  supplier_id TEXT NOT NULL,
  department_id TEXT NOT NULL,
  budget_id TEXT NOT NULL,
  buyer_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  rfq_id TEXT,
  quote_id TEXT,
  issued_at TIMESTAMP NOT NULL,
  currency_code TEXT NOT NULL,
  payment_terms TEXT NOT NULL,
  incoterm TEXT NOT NULL,
  promised_date DATE NOT NULL,
  goods_amount NUMERIC(14,2) NOT NULL,
  freight_amount NUMERIC(14,2) NOT NULL,
  total_amount NUMERIC(14,2) NOT NULL,
  fx_rate_to_usd NUMERIC(12,6) NOT NULL,
  est_duty_usd NUMERIC(14,2) NOT NULL,
  total_usd NUMERIC(14,2) NOT NULL,
  status TEXT NOT NULL,
  closed_at TIMESTAMP,
  PRIMARY KEY (po_id),
  FOREIGN KEY (supplier_id) REFERENCES supplier (supplier_id),
  FOREIGN KEY (department_id) REFERENCES department (department_id),
  FOREIGN KEY (budget_id) REFERENCES budget (budget_id),
  FOREIGN KEY (buyer_id) REFERENCES requester (requester_id),
  FOREIGN KEY (rfq_id) REFERENCES rfq (rfq_id),
  FOREIGN KEY (quote_id) REFERENCES supplier_quote (quote_id),
  CHECK (source_type IS NULL OR source_type IN ('RFQ_AWARD', 'DIRECT_CONTRACT')),
  CHECK (currency_code IS NULL OR currency_code IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'INR', 'CNY')),
  CHECK (payment_terms IS NULL OR payment_terms IN ('NET30', 'NET45', 'NET60')),
  CHECK (incoterm IS NULL OR incoterm IN ('DDP', 'DAP', 'FCA', 'FOB', 'EXW')),
  CHECK (status IS NULL OR status IN ('ISSUED', 'PARTIALLY_RECEIVED', 'RECEIVED', 'CLOSED_SHORT'))
);

CREATE TABLE po_line (
  po_line_id TEXT NOT NULL,
  po_id TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  pr_id TEXT NOT NULL,
  pr_line_id TEXT NOT NULL,
  quote_line_id TEXT,
  item_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit_price NUMERIC(14,2) NOT NULL,
  line_amount NUMERIC(14,2) NOT NULL,
  qty_received INTEGER NOT NULL,
  line_status TEXT NOT NULL,
  PRIMARY KEY (po_line_id),
  FOREIGN KEY (po_id) REFERENCES purchase_order (po_id),
  FOREIGN KEY (pr_id) REFERENCES purchase_request (pr_id),
  FOREIGN KEY (pr_line_id) REFERENCES request_line (pr_line_id),
  FOREIGN KEY (quote_line_id) REFERENCES quote_line (quote_line_id),
  FOREIGN KEY (item_id) REFERENCES item (item_id),
  UNIQUE (po_id, line_no),
  CHECK (line_status IS NULL OR line_status IN ('OPEN', 'PARTIALLY_RECEIVED', 'RECEIVED', 'CLOSED_SHORT'))
);

CREATE TABLE delivery (
  delivery_id TEXT NOT NULL,
  po_id TEXT NOT NULL,
  delivery_seq INTEGER NOT NULL,
  carrier TEXT NOT NULL,
  delivered_at TIMESTAMP NOT NULL,
  received_by TEXT NOT NULL,
  is_on_time BOOLEAN NOT NULL,
  days_late INTEGER NOT NULL,
  completes_po BOOLEAN NOT NULL,
  PRIMARY KEY (delivery_id),
  FOREIGN KEY (po_id) REFERENCES purchase_order (po_id),
  FOREIGN KEY (received_by) REFERENCES requester (requester_id),
  UNIQUE (po_id, delivery_seq)
);

CREATE TABLE delivery_line (
  delivery_line_id TEXT NOT NULL,
  delivery_id TEXT NOT NULL,
  po_line_id TEXT NOT NULL,
  qty_delivered INTEGER NOT NULL,
  qty_accepted INTEGER NOT NULL,
  qty_rejected INTEGER NOT NULL,
  rejection_reason TEXT,
  PRIMARY KEY (delivery_line_id),
  FOREIGN KEY (delivery_id) REFERENCES delivery (delivery_id),
  FOREIGN KEY (po_line_id) REFERENCES po_line (po_line_id),
  CHECK (rejection_reason IS NULL OR rejection_reason IN ('DAMAGED', 'QUALITY_FAIL', 'WRONG_ITEM'))
);

CREATE TABLE budget_transaction (
  budget_txn_id TEXT NOT NULL,
  budget_id TEXT NOT NULL,
  txn_ts TIMESTAMP NOT NULL,
  txn_type TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  allocated_delta_usd NUMERIC(14,2) NOT NULL,
  reserved_delta_usd NUMERIC(14,2) NOT NULL,
  committed_delta_usd NUMERIC(14,2) NOT NULL,
  note TEXT,
  PRIMARY KEY (budget_txn_id),
  FOREIGN KEY (budget_id) REFERENCES budget (budget_id),
  CHECK (txn_type IS NULL OR txn_type IN ('RESERVE', 'RESERVE_ADJUST', 'RELEASE', 'COMMIT', 'DECOMMIT', 'TRANSFER_IN', 'TRANSFER_OUT')),
  CHECK (source_type IS NULL OR source_type IN ('PURCHASE_REQUEST', 'PURCHASE_ORDER', 'APPROVAL'))
);

CREATE TABLE budget_balance (
  budget_id TEXT NOT NULL,
  allocated_original_usd NUMERIC(14,2) NOT NULL,
  transfers_net_usd NUMERIC(14,2) NOT NULL,
  allocated_current_usd NUMERIC(14,2) NOT NULL,
  reserved_usd NUMERIC(14,2) NOT NULL,
  committed_usd NUMERIC(14,2) NOT NULL,
  available_usd NUMERIC(14,2) NOT NULL,
  utilization_pct NUMERIC(6,4) NOT NULL,
  PRIMARY KEY (budget_id),
  FOREIGN KEY (budget_id) REFERENCES budget (budget_id)
);

CREATE TABLE status_event (
  event_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  event_ts TIMESTAMP NOT NULL,
  actor_id TEXT,
  reason TEXT,
  PRIMARY KEY (event_id),
  FOREIGN KEY (actor_id) REFERENCES requester (requester_id),
  CHECK (entity_type IS NULL OR entity_type IN ('PURCHASE_REQUEST', 'RFQ', 'SUPPLIER_QUOTE', 'PURCHASE_ORDER'))
);

CREATE TABLE exception_register (
  exception_id TEXT NOT NULL,
  exception_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  pr_id TEXT,
  raised_at TIMESTAMP NOT NULL,
  reason_code TEXT NOT NULL,
  reason_text TEXT NOT NULL,
  approval_id TEXT,
  resolution TEXT NOT NULL,
  resolved_at TIMESTAMP,
  PRIMARY KEY (exception_id),
  FOREIGN KEY (pr_id) REFERENCES purchase_request (pr_id),
  FOREIGN KEY (approval_id) REFERENCES approval (approval_id),
  CHECK (exception_type IS NULL OR exception_type IN ('BUDGET_EXCEPTION', 'SINGLE_SOURCE', 'COMPETITION_WAIVER', 'NON_LOWEST_AWARD', 'QUOTE_EXPIRED', 'SUPPLIER_DISQUALIFIED', 'LATE_DELIVERY', 'PARTIAL_DELIVERY', 'QUALITY_REJECTION', 'SHORT_CLOSE')),
  CHECK (entity_type IS NULL OR entity_type IN ('PURCHASE_REQUEST', 'RFQ', 'SUPPLIER_QUOTE', 'PURCHASE_ORDER', 'DELIVERY')),
  CHECK (resolution IS NULL OR resolution IN ('APPROVED', 'REJECTED', 'PENDING', 'WITHDRAWN', 'EXCLUDED', 'RECORDED'))
);
