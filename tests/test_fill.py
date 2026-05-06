"""Round-trip fill tests: fill -> re-extract -> assert values."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from oc_pdf_filler.extract import extract_fields
from oc_pdf_filler.fill import fill_pdf
from oc_pdf_filler.backends import DEFAULT_ORDER
from oc_pdf_filler.models import FieldType

PDF_DIR = Path(__file__).parent.parent / "test_pdfs"
VORBLATT = PDF_DIR / "VFNM-2018-05-22-mustervorlage-vorblatt.pdf"
KUNDEN = PDF_DIR / "VFNM-2018-05-22-muster-004-Kundenverwaltung-verarbeitung.pdf"

AVAILABLE = [b for b in DEFAULT_ORDER if b.available()]
AVAILABLE_IDS = [b.name for b in AVAILABLE]


@pytest.fixture
def out_pdf(tmp_path):
    return tmp_path / "out.pdf"


@pytest.mark.parametrize("backend_cls", AVAILABLE, ids=AVAILABLE_IDS)
def test_text_fill_roundtrip(backend_cls, out_pdf):
    values = {
        "Name Verantwortlicher": "Test GmbH",
        "Ort Verantwortlicher": "Berlin",
        "Postleitzahl Verantwortlicher": "10115",
    }
    res = backend_cls().fill(VORBLATT, values, out_pdf)
    assert res.success, f"{backend_cls.name} failed: {res.error} failed={res.failed_fields}"
    fields = {f.name: f for f in extract_fields(out_pdf)}
    for name, expected in values.items():
        assert name in fields
        assert fields[name].value == expected, (
            f"{backend_cls.name}: {name} got {fields[name].value!r} expected {expected!r}"
        )


@pytest.mark.parametrize("backend_cls", AVAILABLE, ids=AVAILABLE_IDS)
def test_checkbox_fill_roundtrip(backend_cls, out_pdf):
    fields = extract_fields(KUNDEN)
    checkboxes = [f for f in fields if f.type == FieldType.CHECKBOX]
    if not checkboxes:
        pytest.skip("no checkbox fields in fixture")
    target = checkboxes[0]
    values = {target.name: True}
    res = backend_cls().fill(KUNDEN, values, out_pdf)
    assert res.success or target.name in res.filled_fields, (
        f"{backend_cls.name}: {res.error} failed={res.failed_fields}"
    )
    after = {f.name: f for f in extract_fields(out_pdf)}
    val = after[target.name].value
    # value should not be Off / 0 / empty
    assert val and str(val).lower() not in {"off", "0", "false", ""}, (
        f"{backend_cls.name}: checkbox {target.name} value={val!r}"
    )


def test_orchestrator_auto(out_pdf):
    values = {"Name Verantwortlicher": "Auto Backend"}
    final, attempts = fill_pdf(VORBLATT, values, out_pdf, backend="auto")
    assert final.success, f"orchestrator failed: {final.error}"
    assert attempts, "expected at least one attempt"
    fields = {f.name: f for f in extract_fields(out_pdf)}
    assert fields["Name Verantwortlicher"].value == "Auto Backend"


def test_cli_extract_smoke(tmp_path):
    out = tmp_path / "fields.json"
    env = {**os.environ, "OC_PDF_FILLER_WORKSPACE": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "-m", "oc_pdf_filler.cli", "extract", str(VORBLATT), "-o", str(out)],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text())
    assert data["field_count"] == 27


def test_cli_fill_smoke(tmp_path):
    values_path = tmp_path / "v.json"
    values_path.write_text(json.dumps({"Name Verantwortlicher": "CLI Test"}))
    out = tmp_path / "out.pdf"
    env = {**os.environ, "OC_PDF_FILLER_WORKSPACE": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "-m", "oc_pdf_filler.cli", "fill",
         str(VORBLATT), str(values_path), "-o", str(out)],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    fields = {f.name: f.value for f in extract_fields(out)}
    assert fields["Name Verantwortlicher"] == "CLI Test"


def test_cli_fill_default_output_in_workspace(tmp_path):
    values_path = tmp_path / "v.json"
    values_path.write_text(json.dumps({"Name Verantwortlicher": "WS Default"}))
    env = {**os.environ, "OC_PDF_FILLER_WORKSPACE": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "-m", "oc_pdf_filler.cli", "fill",
         str(VORBLATT), str(values_path)],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    expected = tmp_path / f"{VORBLATT.stem}_done.pdf"
    assert expected.exists(), f"expected default output at {expected}"


def test_cli_fill_reroutes_outside_workspace(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    values_path = workspace / "v.json"
    values_path.write_text(json.dumps({"Name Verantwortlicher": "Reroute"}))
    bad_out = outside / "evil.pdf"
    env = {**os.environ, "OC_PDF_FILLER_WORKSPACE": str(workspace)}
    proc = subprocess.run(
        [sys.executable, "-m", "oc_pdf_filler.cli", "fill",
         str(VORBLATT), str(values_path), "-o", str(bad_out)],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert not bad_out.exists()
    assert (workspace / "evil.pdf").exists()
