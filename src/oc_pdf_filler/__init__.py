"""oc-pdf-filler: extract and fill PDF AcroForm fields with backend fallback."""

from .models import FieldInfo, FieldType, FillResult
from .extract import extract_fields
from .fill import fill_pdf, available_backends

__all__ = [
    "FieldInfo",
    "FieldType",
    "FillResult",
    "extract_fields",
    "fill_pdf",
    "available_backends",
]
__version__ = "0.1.4"
