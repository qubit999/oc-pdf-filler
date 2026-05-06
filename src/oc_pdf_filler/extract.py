"""Extract AcroForm field metadata from a PDF using pypdf."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.generic import IndirectObject

from .models import FieldInfo, FieldType


_FF_READONLY = 1 << 0
_FF_REQUIRED = 1 << 1
_FF_MULTILINE = 1 << 12
_FF_PASSWORD = 1 << 13
_FF_RADIO = 1 << 15
_FF_PUSHBUTTON = 1 << 16
_FF_COMBO = 1 << 17


def _resolve(obj: Any) -> Any:
    if isinstance(obj, IndirectObject):
        return obj.get_object()
    return obj


def _classify(ft: str | None, ff: int) -> FieldType:
    if ft == "/Tx":
        return FieldType.TEXT
    if ft == "/Btn":
        if ff & _FF_PUSHBUTTON:
            return FieldType.PUSHBUTTON
        if ff & _FF_RADIO:
            return FieldType.RADIO
        return FieldType.CHECKBOX
    if ft == "/Ch":
        return FieldType.CHOICE
    if ft == "/Sig":
        return FieldType.SIGNATURE
    return FieldType.UNKNOWN


def _kid_options(field_dict: Any) -> list[str]:
    """Pull export-value option names from a button field's kid widgets."""
    options: list[str] = []
    kids = _resolve(field_dict.get("/Kids"))
    if not kids:
        return options
    for kid in kids:
        kid = _resolve(kid)
        ap = _resolve(kid.get("/AP"))
        if not ap:
            continue
        n = _resolve(ap.get("/N"))
        if not n:
            continue
        for key in n.keys():
            k = str(key)
            if k != "/Off" and k not in options:
                options.append(k.lstrip("/"))
    return options


def _checkbox_on_value(field_dict: Any) -> str:
    """Detect the export value used for the 'on' state of a checkbox."""
    ap = _resolve(field_dict.get("/AP"))
    if ap:
        n = _resolve(ap.get("/N"))
        if n:
            for key in n.keys():
                k = str(key)
                if k != "/Off":
                    return k.lstrip("/")
    return "Yes"


def _page_index_for_field(reader: PdfReader, field_dict: Any) -> int | None:
    target = field_dict
    page_ref = _resolve(field_dict.get("/P"))
    if page_ref is None:
        kids = _resolve(field_dict.get("/Kids"))
        if kids:
            page_ref = _resolve(_resolve(kids[0]).get("/P"))
    if page_ref is None:
        return None
    for i, page in enumerate(reader.pages):
        if page.indirect_reference and page_ref == page.get_object():
            return i + 1
    return None


def extract_fields(pdf_path: str | Path) -> list[FieldInfo]:
    reader = PdfReader(str(pdf_path))
    raw = reader.get_fields() or {}
    out: list[FieldInfo] = []
    for name, fobj in raw.items():
        fd = _resolve(fobj)
        ft = fd.get("/FT")
        ft_str = str(ft) if ft is not None else None
        ff = int(fd.get("/Ff", 0) or 0)
        ftype = _classify(ft_str, ff)

        value = fd.get("/V")
        if value is not None:
            value = _resolve(value)
            if hasattr(value, "get_object"):
                value = value.get_object()
            value = str(value).lstrip("/") if not isinstance(value, str) else value

        options: list[str] = []
        if ftype == FieldType.RADIO:
            options = _kid_options(fd)
        elif ftype == FieldType.CHOICE:
            opt = _resolve(fd.get("/Opt"))
            if opt:
                for o in opt:
                    o = _resolve(o)
                    if isinstance(o, list) and len(o) >= 2:
                        options.append(str(_resolve(o[1])))
                    else:
                        options.append(str(o))
        elif ftype == FieldType.CHECKBOX:
            options = [_checkbox_on_value(fd), "Off"]

        max_len = fd.get("/MaxLen")
        if max_len is not None:
            try:
                max_len = int(max_len)
            except Exception:
                max_len = None

        out.append(
            FieldInfo(
                name=str(name),
                type=ftype,
                page=_page_index_for_field(reader, fd),
                value=value,
                options=options,
                max_length=max_len,
                required=bool(ff & _FF_REQUIRED),
                multiline=bool(ff & _FF_MULTILINE),
                read_only=bool(ff & _FF_READONLY),
            )
        )
    return out


def extract_to_dict(pdf_path: str | Path) -> dict:
    fields = extract_fields(pdf_path)
    return {
        "path": str(pdf_path),
        "field_count": len(fields),
        "fields": [f.to_dict() for f in fields],
    }
