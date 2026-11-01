"""Anomaly plan and ground-truth recorder.

Pipeline: a baseline run (no injection) counts, per anomaly type, the opportunities where the
anomaly could occur.  The plan then picks evenly spaced opportunity indices so injected cases
are spread over the year, and the injected run applies them.  Every applied case is written to
ground truth with the rule it violates and the evidence; nothing is flagged inside the data.
"""
from __future__ import annotations

import json

SPECS = {
    "PO_WITHOUT_APPROVAL": ("HIGH", "CTL-APR: PO may be issued only after every required approval step is APPROVED",
                            "Hold the PO until the approval chain completes"),
    "QUOTE_EXPIRED_AT_AWARD": ("MEDIUM", "CTL-QVAL: awarded quote must be valid on the award date",
                               "Request a validity extension or award the best valid quote"),
    "NON_LOWEST_AWARD_NO_RATIONALE": ("HIGH", "CTL-AWD: award to other than the lowest eligible landed cost needs a documented basis",
                                      "Award to the lowest eligible landed cost or document the rationale"),
    "INACTIVE_SUPPLIER": ("HIGH", "CTL-SUP: POs may only be issued to suppliers ACTIVE on the PO date",
                          "Issue the PO to the active contract supplier"),
    "BUDGET_OVERRUN": ("HIGH", "CTL-BUD: over-budget spend needs an approved BUDGET_EXCEPTION before commitment",
                       "Route to Finance for a budget exception or reject"),
    "DUPLICATE_REQUEST": ("MEDIUM", "CTL-DUP: same requester, category and lines within 10 days is a duplicate",
                          "Reject or cancel the later request as a duplicate"),
    "QUOTE_CURRENCY_MISMATCH": ("HIGH", "CTL-CCY: PO currency must equal the awarded quote currency",
                                "Issue the PO in the quote currency (or convert prices at the published rate)"),
    "SPLIT_PURCHASE": ("MEDIUM", "CTL-SPLIT: related requests may not be split to stay under an approval or RFQ threshold",
                       "Consolidate into one request and apply the combined threshold"),
}
DES_TYPES = ("PO_WITHOUT_APPROVAL", "BUDGET_OVERRUN", "INACTIVE_SUPPLIER", "QUOTE_CURRENCY_MISMATCH")


class AnomalyPlan:
    def __init__(self, cfg, targets: dict | None = None):
        self.cfg = cfg
        self.targets = {k: set(v) for k, v in (targets or {}).items()}
        self.counts = {k: 0 for k in DES_TYPES}
        self.tainted: set[str] = set()      # request ids already carrying an anomaly

    def chance(self, name: str, pr_ids) -> bool:
        """Register one opportunity; True when this opportunity was planned as an anomaly."""
        pr_ids = [pr_ids] if isinstance(pr_ids, str) else list(pr_ids)
        if any(p in self.tainted for p in pr_ids):
            return False
        i = self.counts[name]
        self.counts[name] += 1
        if i in self.targets.get(name, ()):
            self.tainted.update(pr_ids)
            return True
        return False

    @classmethod
    def from_baseline(cls, cfg, baseline_counts: dict) -> "AnomalyPlan":
        targets = {}
        for name in DES_TYPES:
            quota, n = cfg.anomaly_quota(name), baseline_counts.get(name, 0)
            usable = max(1, int(n * 0.75)) if n else 0   # head-room: knock-on effects can remove a few
            if quota and usable:
                quota = min(quota, usable)
                targets[name] = {int((j + 0.5) * usable / quota) for j in range(quota)}
        return cls(cfg, targets)


class GroundTruth:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, issue_type: str, sub_type: str, entity_type: str, entity_id: str,
            related=(), description: str = "", **evidence) -> dict:
        severity, rule, expected = SPECS[issue_type]
        self.rows.append({"issue_type": issue_type, "sub_type": sub_type, "severity": severity,
                          "entity_type": entity_type, "entity_id": entity_id,
                          "related_ids": "|".join(related), "control_rule": rule,
                          "expected_handling": expected, "description": description,
                          "evidence": evidence})
        return self.rows[-1]

    def resolve_pr_keys(self, key_to_id: dict) -> None:
        """Requests are numbered after injection; swap internal '@key' placeholders for PR ids."""
        def fix(v):
            if isinstance(v, str):
                return "|".join(key_to_id.get(p[1:], p) if p.startswith("@") else p for p in v.split("|"))
            if isinstance(v, list):
                return [fix(x) for x in v]
            return v
        for row in self.rows:
            for k in ("entity_id", "related_ids"):
                row[k] = fix(row[k])
            row["evidence"] = {k: fix(v) for k, v in row["evidence"].items()}

    def finalize(self) -> list[dict]:
        out = sorted(self.rows, key=lambda r: (r["issue_type"], r["entity_id"]))
        for n, row in enumerate(out, 1):
            row["gt_id"] = f"GT-{n:05d}"
            row["evidence"] = json.dumps(row["evidence"], sort_keys=True, default=str)
        cols = ("gt_id", "issue_type", "sub_type", "severity", "entity_type", "entity_id", "related_ids",
                "control_rule", "expected_handling", "description", "evidence")
        return [{c: row[c] for c in cols} for row in out]
