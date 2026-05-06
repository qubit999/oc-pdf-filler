"""Backend implementations for filling PDF forms."""

from .base import FillBackend
from .pypdf_backend import PypdfBackend
from .pdfrw_backend import PdfrwBackend
from .pymupdf_backend import PymupdfBackend
from .pdftk_backend import PdftkBackend

DEFAULT_ORDER: list[type[FillBackend]] = [
    PypdfBackend,
    PdfrwBackend,
    PymupdfBackend,
    PdftkBackend,
]

__all__ = [
    "FillBackend",
    "PypdfBackend",
    "PdfrwBackend",
    "PymupdfBackend",
    "PdftkBackend",
    "DEFAULT_ORDER",
]
