"""PyMuPDF (fitz) fill backend (optional dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import FillResult
from .base import FillBackend, coerce_checkbox


class PymupdfBackend(FillBackend):
    name = "pymupdf"

    @classmethod
    def available(cls) -> bool:
        try:
            import fitz  # noqa: F401
            return True
        except ImportError:
            return False

    def fill(self, input_path, values, output_path, *, flatten=False) -> FillResult:
        try:
            import fitz
        except ImportError as exc:
            return FillResult(self.name, False, error=str(exc))

        try:
            doc = fitz.open(str(input_path))
        except Exception as exc:
            return FillResult(self.name, False, error=f"open failed: {exc}")

        # Process widgets within their page iteration (PyMuPDF widget objects
        # become invalid once their owning page is GC'd or another page is iterated).
        filled: list[str] = []
        failed: list[str] = []
        seen_names: set[str] = set()

        for page in doc:
            for w in page.widgets() or []:
                name = w.field_name
                if not name or name not in values:
                    continue
                seen_names.add(name)
                raw_value = values[name]
                ft = w.field_type
                try:
                    if ft == fitz.PDF_WIDGET_TYPE_TEXT:
                        w.field_value = str(raw_value)
                        w.update()
                    elif ft == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                        on = bool(coerce_checkbox(raw_value))
                        try:
                            w.field_value = on
                            w.update()
                        except Exception:
                            states = (w.button_states() or {}).get("normal") or ["Yes"]
                            on_name = next((s for s in states if s != "Off"), "Yes")
                            w.field_value = on_name if on else "Off"
                            w.update()
                    elif ft == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                        opt = str(raw_value).lstrip("/")
                        states = (w.button_states() or {}).get("normal") or []
                        normal = [s.lstrip("/") for s in states]
                        w.field_value = opt if opt in normal else False
                        w.update()
                    elif ft in (
                        getattr(fitz, "PDF_WIDGET_TYPE_COMBOBOX", -1),
                        getattr(fitz, "PDF_WIDGET_TYPE_LISTBOX", -1),
                    ):
                        w.field_value = str(raw_value)
                        w.update()
                    else:
                        if name not in failed:
                            failed.append(name)
                        continue
                    if name not in filled:
                        filled.append(name)
                except Exception:
                    if name not in failed:
                        failed.append(name)

        missing = [k for k in values.keys() if k not in seen_names]

        try:
            if flatten and hasattr(doc, "bake"):
                doc.bake()
            doc.save(str(output_path), incremental=False, deflate=True)
            doc.close()
        except Exception as exc:
            return FillResult(self.name, False, filled, missing, failed,
                              error=f"write failed: {exc}")

        return FillResult(
            backend=self.name,
            success=not failed and not missing,
            filled_fields=filled,
            missing_fields=missing,
            failed_fields=failed,
        )
