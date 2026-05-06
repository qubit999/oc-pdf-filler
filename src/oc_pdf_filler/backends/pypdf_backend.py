"""pypdf-based fill backend.

Handles text fields, checkboxes, and radio buttons by walking AcroForm
fields and updating per-page widget annotations directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import FillResult
from .base import FillBackend, coerce_checkbox


class PypdfBackend(FillBackend):
    name = "pypdf"

    @classmethod
    def available(cls) -> bool:
        try:
            import pypdf  # noqa: F401
            return True
        except ImportError:
            return False

    def fill(self, input_path, values, output_path, *, flatten=False) -> FillResult:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import (
            BooleanObject,
            NameObject,
            TextStringObject,
            NumberObject,
        )

        try:
            reader = PdfReader(str(input_path))
            writer = PdfWriter(clone_from=reader)
        except Exception as exc:
            return FillResult(self.name, False, error=f"open failed: {exc}")

        # Use writer-side field dicts so mutations end up in the output.
        fields = writer.get_fields() or reader.get_fields() or {}
        if not fields:
            return FillResult(self.name, False, error="no AcroForm fields detected")

        # Ensure /NeedAppearances so viewers regenerate field appearances.
        try:
            root = writer._root_object
            if "/AcroForm" in root:
                root["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)
        except Exception:
            pass

        filled: list[str] = []
        failed: list[str] = []
        missing = [k for k in values.keys() if k not in fields]

        # Build map: field name -> classification helper
        from ..extract import _classify, _resolve, _checkbox_on_value, _kid_options

        # Iterate every page widget so we can match by /T name reliably.
        # Some fields live in field tree as parents with kids on pages.
        widgets_by_name: dict[str, list] = {}

        def _full_name(annot):
            parts = []
            cur = annot
            seen = set()
            while cur is not None and id(cur) not in seen:
                seen.add(id(cur))
                t = cur.get("/T")
                if t is not None:
                    parts.append(str(t))
                parent = cur.get("/Parent")
                if parent is None:
                    break
                cur = _resolve(parent)
            return ".".join(reversed(parts)) if parts else None

        for page in writer.pages:
            annots = page.get("/Annots")
            if annots is None:
                continue
            for a in annots:
                a = _resolve(a)
                if a.get("/Subtype") != "/Widget" and "/T" not in a:
                    continue
                fname = _full_name(a)
                if fname:
                    widgets_by_name.setdefault(fname, []).append(a)

        for name, raw_value in values.items():
            if name not in fields:
                continue
            fd = _resolve(fields[name])
            ft = str(fd.get("/FT", ""))
            ff = int(fd.get("/Ff", 0) or 0)
            try:
                if ft == "/Tx":
                    fd[NameObject("/V")] = TextStringObject(str(raw_value))
                    if "/AP" in fd:
                        del fd["/AP"]
                    for w in widgets_by_name.get(name, []):
                        w[NameObject("/V")] = TextStringObject(str(raw_value))
                        if "/AP" in w:
                            del w["/AP"]
                    filled.append(name)
                elif ft == "/Btn":
                    is_radio = bool(ff & (1 << 15))
                    is_push = bool(ff & (1 << 16))
                    if is_push:
                        failed.append(name)
                        continue
                    if is_radio:
                        opt = str(raw_value)
                        target = "/" + opt.lstrip("/")
                        fd[NameObject("/V")] = NameObject(target)
                        for kid in (fd.get("/Kids") or []):
                            kid = _resolve(kid)
                            ap = _resolve(kid.get("/AP")) or {}
                            n = _resolve(ap.get("/N")) or {}
                            keys = [str(k) for k in n.keys()]
                            kid[NameObject("/AS")] = NameObject(
                                target if target in keys else "/Off"
                            )
                        filled.append(name)
                    else:
                        # Determine the export "on" name from any widget AP/N or the field itself.
                        widgets = widgets_by_name.get(name, [])
                        on_val = None
                        for src in [fd] + widgets:
                            ap = _resolve(src.get("/AP")) if src.get("/AP") else None
                            n = _resolve(ap.get("/N")) if ap else None
                            if n:
                                for k in n.keys():
                                    ks = str(k)
                                    if ks != "/Off":
                                        on_val = ks
                                        break
                            if on_val:
                                break
                        on_val = on_val or "/Yes"
                        new_state = on_val if coerce_checkbox(raw_value) else "/Off"
                        fd[NameObject("/V")] = NameObject(new_state)
                        fd[NameObject("/AS")] = NameObject(new_state)
                        for w in widgets:
                            w[NameObject("/V")] = NameObject(new_state)
                            w[NameObject("/AS")] = NameObject(new_state)
                        filled.append(name)
                elif ft == "/Ch":
                    fd[NameObject("/V")] = TextStringObject(str(raw_value))
                    for w in widgets_by_name.get(name, []):
                        w[NameObject("/V")] = TextStringObject(str(raw_value))
                    filled.append(name)
                else:
                    failed.append(name)
            except Exception:
                failed.append(name)

        try:
            with open(output_path, "wb") as fh:
                writer.write(fh)
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
