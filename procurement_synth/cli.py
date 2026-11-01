"""Command line: generate, validate, reproduce, docs, all."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path

from . import controls, docs, metrics, validate
from .config import DEFAULT_SEED, SCALES, RunConfig
from .export import export, sha256, write_csv
from .generator import generate

ROOT = Path(__file__).resolve().parent.parent


def _live_steps():
    """Progress callback for generate(): one line per run, each stage added as it starts."""
    last = None

    def show(run: str, stage: str) -> None:
        nonlocal last
        if run == last:
            print(f" > {stage}", end="", flush=True)
        else:
            print(("\n" if last else "") + f"      {run + ':':14s}{stage}", end="", flush=True)
            last = run
    return show


def cmd_generate(scale: str, seed: int, out: Path, anomalies: bool = True, quiet: bool = False) -> dict:
    cfg = RunConfig(seed=seed, scale=SCALES[scale], inject_anomalies=anomalies)
    ds = generate(cfg, None if quiet else _live_steps())
    if out.exists():
        for sub in ("csv", "json", "sql", "ground_truth"):
            shutil.rmtree(out / sub, ignore_errors=True)
    if not quiet:
        print(f"\n      {'export:':14s}csv, json, sql, ground_truth, manifest.json", flush=True)
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
        print(f"  reports: {_label(reports)}/ (validation_summary.md, control_findings.csv, metrics.md)")
    return rep.ok


def _shipped_checksums(shipped: Path | None, seed: int) -> tuple[dict | None, str]:
    """path -> (SHA-256 listed in the shipped manifest, SHA-256 of the shipped bytes), or None and why."""
    if shipped is None or not (shipped / "manifest.json").exists():
        return None, "no shipped manifest found"
    manifest = json.loads((shipped / "manifest.json").read_text(encoding="utf-8"))
    if manifest["seed"] != seed:
        return None, f"shipped data was generated with seed {manifest['seed']}"
    return {f["path"]: (f["sha256"], sha256(shipped / f["path"]) if (shipped / f["path"]).exists() else None)
            for f in manifest["files"]}, ""


def _label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def cmd_reproduce(scale: str, seed: int, out: Path, shipped: Path | None = None) -> bool:
    """Generate twice and compare every file; also compare run 1 with the shipped copy when it has this seed."""
    runs = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in (1, 2):
            print("      run 1" if i == 1 else " > run 2", end="", flush=True)
            m = cmd_generate(scale, seed, Path(tmp) / f"run{i}", quiet=True)
            runs.append({f["path"]: (f["rows"], f["sha256"]) for f in m["files"]})
    print()
    same = runs[0] == runs[1]
    ship, why = _shipped_checksums(shipped, seed)
    rows = [{"path": p, "rows": runs[0][p][0], "sha256_run1": runs[0][p][1], "sha256_run2": runs[1][p][1],
             "identical": runs[0][p] == runs[1].get(p),
             "shipped_identical": None if ship is None else ship.get(p) == (runs[0][p][1], runs[0][p][1])}
            for p in sorted(runs[0])]
    shipped_ok = None if ship is None else set(ship) == set(runs[0]) and all(r["shipped_identical"] for r in rows)
    n_shipped = sum(1 for r in rows if r["shipped_identical"])
    label = _label(shipped) if shipped else None
    env = {"python_version": platform.python_version(), "platform": platform.platform(terse=True)}
    out.mkdir(parents=True, exist_ok=True)
    (out / "reproducibility.json").write_text(json.dumps({
        "scale": scale, "seed": seed, "identical": same, **env, "shipped_dir": label,
        "shipped_identical": shipped_ok, "shipped_not_compared_reason": why or None, "files": rows},
        indent=1) + "\n", encoding="utf-8", newline="")
    if ship is None:
        verdict = f"not compared ({why})"
    elif shipped_ok:
        verdict = ("**identical**: every file matches run 1, both by the SHA-256 listed in `manifest.json` "
                   "and by the bytes on disk")
    else:
        verdict = f"**MISMATCH** in {len(rows) - n_shipped} of {len(rows)} files"
    lines = [f"# Reproducibility check - {scale}, seed {seed}", "",
             f"Generated the dataset twice in separate folders with the same seed. "
             f"**{'All files identical' if same else 'MISMATCH'}** ({len(rows)} files compared by row count and SHA-256).", "",
             f"Shipped copy (`{label}`): {verdict}." if shipped else "Shipped copy: not compared.", "",
             f"Environment: Python {env['python_version']} on {env['platform']}.", "",
             "| File | Rows | SHA-256 (run 1) | Same in run 2 | Same as shipped |", "|---|---:|---|:-:|:-:|"]
    lines += [f"| {r['path']} | {r['rows'] if r['rows'] is not None else ''} | `{r['sha256_run1'][:16]}...` | "
              f"{'yes' if r['identical'] else '**no**'} | "
              f"{'n/a' if r['shipped_identical'] is None else 'yes' if r['shipped_identical'] else '**no**'} |" for r in rows]
    (out / "reproducibility.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    print(f"reproducibility {scale}: {'identical' if same else 'MISMATCH'} across {len(rows)} files")
    print(f"  shipped {label} matches: {n_shipped}/{len(rows)} files" if ship is not None
          else f"  shipped copy not compared: {why}")
    return same and shipped_ok is not False


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
        shipped = ROOT / "data" / args.scale
        return 0 if cmd_reproduce(args.scale, args.seed, shipped / "reports", shipped) else 1
    dictionary = ROOT / "docs" / "data_dictionary.md"
    if args.cmd == "docs":
        docs.write_data_dictionary(dictionary)
        print(f"wrote {_label(dictionary)}")
        return 0
    ok, started = True, time.perf_counter()
    print(f"procurement_synth all, seed {args.seed}: starter (10%), then full (brief volumes)")
    for scale in ("starter", "full"):
        out = ROOT / "data" / scale
        print(f"\n=== {scale} {'=' * (67 - len(scale))}")
        print("[1/3] Generate: pipeline stages run twice, baseline first, then with labelled edge cases")
        cmd_generate(scale, args.seed, out)
        print("[2/3] Validate: schema, keys, dates, amounts, business rules, ground truth; controls; metrics")
        ok &= cmd_validate(out)
        print("[3/3] Reproduce: generate twice more in a temp folder, compare every file's SHA-256")
        ok &= cmd_reproduce(scale, args.seed, out / "reports", out)
    docs.write_data_dictionary(dictionary)
    print(f"\n[docs] {_label(dictionary)} rebuilt from the schema")
    took = f"{time.perf_counter() - started:.1f} s"
    print(f"\nRESULT: PASS - every stage passed for starter and full ({took})" if ok
          else f"\nRESULT: FAIL - see the FAIL / MISMATCH lines above ({took})")
    print("Start with data/full/reports/validation_summary.md and data/full/reports/metrics.md")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
