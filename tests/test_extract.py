import json
from pathlib import Path

from oc_pdf_filler.extract import extract_fields, extract_to_dict
from oc_pdf_filler.models import FieldType

PDF_DIR = Path(__file__).parent.parent / "test_pdfs"

EXPECTED = {
    "A1 Antrag auf Eintragung.pdf": 66,
    "VFNM-2018-05-22-muster-004-Kundenverwaltung-verarbeitung.pdf": 57,
    "VFNM-2018-05-22-mustervorlage-vorblatt.pdf": 27,
}


def test_field_counts():
    for name, count in EXPECTED.items():
        fields = extract_fields(PDF_DIR / name)
        assert len(fields) == count, f"{name}: expected {count} got {len(fields)}"


def test_classification_vorblatt():
    fields = extract_fields(PDF_DIR / "VFNM-2018-05-22-mustervorlage-vorblatt.pdf")
    assert all(f.type == FieldType.TEXT for f in fields)


def test_classification_kundenverwaltung_has_buttons():
    fields = extract_fields(
        PDF_DIR / "VFNM-2018-05-22-muster-004-Kundenverwaltung-verarbeitung.pdf"
    )
    types = {f.type for f in fields}
    assert FieldType.TEXT in types
    assert FieldType.CHECKBOX in types or FieldType.RADIO in types


def test_extract_to_dict_serializable():
    data = extract_to_dict(PDF_DIR / "VFNM-2018-05-22-mustervorlage-vorblatt.pdf")
    json.dumps(data)  # must round-trip JSON
    assert data["field_count"] == 27
