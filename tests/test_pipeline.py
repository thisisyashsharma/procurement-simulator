"""End-to-end tests: generate -> export -> validate, reproducibility and ground-truth separation."""
from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from procurement_synth import cli, controls, validate
from procurement_synth.anomalies import SPECS
from procurement_synth.config import DEFAULT_SEED, SCALES, RunConfig
from procurement_synth.export import export
from procurement_synth.generator import generate


@pytest.fixture(scope="module")
def starter(tmp_path_factory):
    out = tmp_path_factory.mktemp("starter")
    ds = generate(RunConfig(scale=SCALES["starter"]))
    manifest = export(ds, out)
    return ds, out, manifest


def test_starter_passes_every_validation_check(starter):
    _, out, _ = starter
    rep = validate.run(out)
    failing = [r for r in rep.rows if not r["passed"]]
    assert not failing, failing[:5]


def test_every_required_edge_case_is_injected_and_detected(starter):
    ds, _, _ = starter
    counts = Counter(g["issue_type"] for g in ds.ground_truth)
    required = set(SPECS)
    assert required <= set(counts), counts
    found = {(f["issue_type"], f["entity_id"]) for f in controls.detect(ds.tables)}
    labelled = {(g["issue_type"], g["entity_id"]) for g in ds.ground_truth}
    assert found == labelled


def test_clean_baseline_has_no_control_findings(starter):
    ds, _, _ = starter
    assert controls.detect(ds.baseline.tables) == []
    assert controls.illegal_transitions(ds.baseline.tables) == []


def test_same_seed_is_byte_identical(tmp_path, starter):
    _, _, first = starter
    stages = []
    ds = generate(RunConfig(scale=SCALES["starter"]), progress=lambda run, stage: stages.append((run, stage)))
    second = export(ds, tmp_path)                 # reporting progress must not change a byte
    assert [(f["path"], f["sha256"]) for f in first["files"]] == [(f["path"], f["sha256"]) for f in second["files"]]
    pipeline = ["master data", "demand", "budgets", "sourcing", "process simulation", "finalize"]
    assert stages == [("baseline run", s) for s in pipeline] + [("injected run", s) for s in pipeline]


def test_different_seed_changes_data(tmp_path, starter):
    _, _, first = starter
    other = export(generate(RunConfig(seed=7, scale=SCALES["starter"])), tmp_path)
    assert {f["sha256"] for f in first["files"]} != {f["sha256"] for f in other["files"]}


def test_manifest_lists_provenance_fields(starter):
    _, _, manifest = starter
    prov = manifest["provenance"]
    assert prov["external_data"] == []
    for key in ("source_url", "dataset_version", "retrieval_date", "source_license_terms", "attribution",
                "transformations", "fields_discarded", "schema_inspiration", "license"):
        assert prov[key], key


def test_reproduce_matches_shipped_copy(tmp_path, starter):
    _, out, _ = starter
    assert cli.cmd_reproduce("starter", DEFAULT_SEED, tmp_path / "ok", shipped=out)
    assert json.loads((tmp_path / "ok" / "reproducibility.json").read_text())["shipped_identical"] is True
    tampered = tmp_path / "tampered"
    shutil.copytree(out, tampered)                # the shared fixture stays untouched
    target = tampered / "csv" / "department.csv"
    data = bytearray(target.read_bytes())
    data[-2] = ord("X") if data[-2] != ord("X") else ord("Y")
    target.write_bytes(bytes(data))
    assert not cli.cmd_reproduce("starter", DEFAULT_SEED, tmp_path / "bad", shipped=tampered)
    report = json.loads((tmp_path / "bad" / "reproducibility.json").read_text())
    assert report["shipped_identical"] is False
    assert [f["path"] for f in report["files"] if not f["shipped_identical"]] == ["csv/department.csv"]


def test_ground_truth_lives_outside_input_folders(starter):
    _, out, _ = starter
    assert not list((out / "csv").glob("*ground*"))
    header = (out / "csv" / "purchase_request.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "issue" not in header and "anomal" not in header


def test_full_scale_hits_the_brief_volumes(tmp_path):
    ds = generate(RunConfig(scale=SCALES["full"]))
    t = ds.tables
    assert (len(t["requester"]), len(t["supplier"]), len(t["purchase_request"]), len(t["rfq"]),
            len(t["supplier_quote"])) == (300, 120, 1200, 500, 1500)
    assert abs(len(t["purchase_order"]) - 900) <= 45
    assert set(Counter(g["issue_type"] for g in ds.ground_truth)) == set(SPECS)
    manifest = export(ds, tmp_path)
    assert json.loads(Path(tmp_path / "manifest.json").read_text())["seed"] == manifest["seed"] == 20261022
