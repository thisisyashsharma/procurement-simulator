"""Command line: generate, validate, reproduce, docs, all."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from . import controls, docs, metrics, validate
from .config import DEFAULT_SEED, SCALES, RunConfig
from .export import export, write_csv
from .generator import generate

ROOT = Path(__file__).resolve().parent.parent


def cmd_generate(scale: str, seed: int, out: Path, anomalies: bool = True, quiet: bool = False) -> dict:
    ds = generate(RunConfig(seed=seed, scale=SCALES[scale], inject_anomalies=anomalies))
    if out.exists():
        for sub in ("csv", "json", "sql", "ground_truth"):
            shutil.rmtree(out / sub, ignore_errors=True)
    manifest = export(ds, out)
    if ds.baseline is not None:
        base = ds.baseline.tables
        (out / "reports").mkdir(parents=True, exist_ok=True)
        clean = controls.detect(base)
        (out / "reports" / "baseline_check.json").write_text(json.dumps({
            "description": "Same seed and scale generated with anomaly injection switched off; the control "
                           "checks must find nothing.",
            "rows": {k: len(v) for k, v in base.items()}, "control_findings": len(clean),
            "illegal_transitions": len(controls.illegal_transitions(base)),
            "anomaly_opportunities_counted": ds.baseline.opportunities}, indent=2) + "\n", encoding="utf-8", newline="")
    if not quiet:
        print(f"generated {scale} (seed {seed}) -> {out}")
        for k, v in manifest["row_counts"].items():
            print(f"  {k:26s} {v:>7}")
        print(f"  ground truth labels        {len(ds.ground_truth):>7}")
    return manifest


def cmd_validate(data: Path, quiet: bool = False) -> bool:
    rep = validate.run(data)
    reports = data / "reports"
    reports.mkdir(exist_ok=True)
    validate.write_report(rep, reports / "validation_summary.md", reports / "validation_summary.json", data.name)
    T, gt, manifest = validate.load(data)
    findings = controls.detect(T)
    write_csv(reports / "control_findings.csv", findings, ["issue_type", "entity_type", "entity_id", "related_ids", "detail"], {})
    metrics.write(T, gt, findings, manifest, reports)
    if not quiet:
        failing = [r for r in rep.rows if not r["passed"]]
        print(f"validation {'PASS' if rep.ok else 'FAIL'}: {len(rep.rows)} checks, {len(failing)} failing")
        for r in failing[:25]:
            print(f"  FAIL [{r['category']}] {r['check']}: {r['failed']} e.g. {r['examples']}")
    return rep.ok


def cmd_reproduce(scale: str, seed: int, out: Path) -> bool:
    runs = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in (1, 2):
            m = cmd_generate(scale, seed, Path(tmp) / f"run{i}", quiet=True)
            runs.append({f["path"]: (f["rows"], f["sha256"]) for f in m["files"]})
    same = runs[0] == runs[1]
    rows = [{"path": p, "rows": runs[0][p][0], "sha256_run1": runs[0][p][1], "sha256_run2": runs[1][p][1],
             "identical": runs[0][p] == runs[1].get(p)} for p in sorted(runs[0])]
    out.mkdir(parents=True, exist_ok=True)
    (out / "reproducibility.json").write_text(json.dumps({"scale": scale, "seed": seed, "identical": same,
                                                          "files": rows}, indent=1) + "\n", encoding="utf-8", newline="")
    lines = [f"# Reproducibility check - {scale}, seed {seed}", "",
             f"Generated the dataset twice in separate folders with the same seed. "
             f"**{'All files identical' if same else 'MISMATCH'}** ({len(rows)} files compared by row count and SHA-256).", "",
             "| File | Rows | SHA-256 (run 1) | Same in run 2 |", "|---|---:|---|:-:|"]
    lines += [f"| {r['path']} | {r['rows'] if r['rows'] is not None else ''} | `{r['sha256_run1'][:16]}...` | "
              f"{'yes' if r['identical'] else '**no**'} |" for r in rows]
    (out / "reproducibility.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    print(f"reproducibility {scale}: {'identical' if same else 'MISMATCH'} across {len(rows)} files")
    return same


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m procurement_synth", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="generate one dataset")
    g.add_argument("--scale", choices=sorted(SCALES), default="full")
    g.add_argument("--seed", type=int, default=DEFAULT_SEED)
    g.add_argument("--out", type=Path)
    g.add_argument("--no-anomalies", action="store_true", help="clean baseline without injected edge cases")
    v = sub.add_parser("validate", help="validate an exported dataset folder")
    v.add_argument("--data", type=Path, required=True)
    r = sub.add_parser("reproduce", help="generate twice and compare checksums")
    r.add_argument("--scale", choices=sorted(SCALES), default="starter")
    r.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sub.add_parser("docs", help="regenerate docs/data_dictionary.md from the schema")
    a = sub.add_parser("all", help="starter + full: generate, validate, reproduce, docs")
    a.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args(argv)
    if args.cmd == "generate":
        cmd_generate(args.scale, args.seed, args.out or ROOT / "data" / args.scale, not args.no_anomalies)
        return 0
    if args.cmd == "validate":
        return 0 if cmd_validate(args.data) else 1
    if args.cmd == "reproduce":
        return 0 if cmd_reproduce(args.scale, args.seed, ROOT / "data" / args.scale / "reports") else 1
    if args.cmd == "docs":
        docs.write_data_dictionary(ROOT / "docs" / "data_dictionary.md")
        return 0
    ok = True
    for scale in ("starter", "full"):
        out = ROOT / "data" / scale
        cmd_generate(scale, args.seed, out)
        ok &= cmd_validate(out)
        ok &= cmd_reproduce(scale, args.seed, out / "reports")
    docs.write_data_dictionary(ROOT / "docs" / "data_dictionary.md")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
