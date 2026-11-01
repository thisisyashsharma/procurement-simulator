"""Pipeline: master data -> demand -> budgets -> sourcing -> process simulation -> finalize.

`generate()` first runs a clean baseline (no injected anomalies) to count where each anomaly
could occur, then re-runs with the anomaly plan.  Both runs use the same per-entity random
streams, so the injected dataset differs from the baseline only at the labelled cases and
their natural knock-on effects (e.g. an overrun leaves less budget for later requests).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .anomalies import AnomalyPlan, GroundTruth
from .budget import build_budgets
from .config import RunConfig
from .demand import build_demand
from .engine import Engine
from .finalize import finalize
from .master import build_master
from .sourcing import plan_sourcing
from .util import EventLog


@dataclass
class Dataset:
    cfg: RunConfig
    tables: dict
    ground_truth: list
    opportunities: dict
    baseline: "Dataset | None" = None
    notes: dict = field(default_factory=dict)


def _run(cfg: RunConfig, plan: AnomalyPlan) -> Dataset:
    w = build_master(cfg)
    gt = GroundTruth()
    prs = build_demand(w, gt)
    build_budgets(w, prs)
    ev = EventLog()
    rfqs = plan_sourcing(w, prs, gt, ev)
    eng = Engine(w, prs, rfqs, plan, gt, ev).run()
    tables = finalize(w, prs, rfqs, eng, ev)
    return Dataset(cfg, tables, gt.finalize(), dict(plan.counts))


def generate(cfg: RunConfig) -> Dataset:
    base_cfg = cfg.with_(inject_anomalies=False)
    baseline = _run(base_cfg, AnomalyPlan(base_cfg))
    if not cfg.inject_anomalies:
        return baseline
    final = _run(cfg, AnomalyPlan.from_baseline(cfg, baseline.opportunities))
    final.baseline = baseline
    return final
