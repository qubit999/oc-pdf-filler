"""pdfrw-based fill backend (optional dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import FillResult
from .base import FillBackend, coerce_checkbox


class PdfrwBackend(FillBackend):
    name = "pdfrw"

    @classmethod
    def available(cls) -> bool:
        try:
            import pdfrw  # noqa: F401
            return True
        except ImportError:
            return False

    def fill(self, input_path, values, output_path, *, flatten=False) -> FillResult:
        try:
            import pdfrw
            from pdfrw import PdfReader, PdfWriter, PdfDict, PdfName, PdfString
        except ImportError as exc:
            return FillResult(self.name, False, error=str(exc))

        try:
            tpl = PdfReader(str(input_path))
        except Exception as exc:
            return FillResult(self.name, False, error=f"open failed: {exc}")

        # Set NeedAppearances so viewers regenerate appearance streams.
        if tpl.Root.AcroForm is None:
            return FillResult(self.name, False, error="no AcroForm")
        tpl.Root.AcroForm.update(PdfDict(NeedAppearances=PdfName("true")))

        # Walk all annotations and build a name index, including inherited /T from /Parent.
        def _full_name(annot):
            parts = []
            cur = annot
            seen = set()
            while cur is not None and id(cur) not in seen:
                seen.add(id(cur))
                if cur.T is not None:
                    parts.append(str(cur.T).strip("()"))
                cur = cur.Parent
            return ".".join(reversed(parts)) if parts else None

        widgets_by_name: dict[str, list] = {}
        for page in tpl.pages:
            annotations = page.Annots or []
            for a in annotations:
                if a.Subtype != PdfName("Widget") and a.T is None:
                    continue
                fname = _full_name(a)
                if fname:
                    widgets_by_name.setdefault(fname, []).append(a)

        # Also walk AcroForm Fields tree to find parent fields not directly on pages.
        def _walk_fields(field, prefix=""):
            name = str(field.T).strip("()") if field.T else ""
            full = (prefix + "." + name) if prefix and name else (name or prefix)
            if full and full not in widgets_by_name:
                widgets_by_name.setdefault(full, []).append(field)
            for kid in (field.Kids or []):
                _walk_fields(kid, full)

        for f in (tpl.Root.AcroForm.Fields or []):
            _walk_fields(f)

        filled: list[str] = []
        failed: list[str] = []
        missing = [k for k in values.keys() if k not in widgets_by_name]

        for name, raw_value in values.items():
            annots = widgets_by_name.get(name)
            if not annots:
                continue
            try:
                primary = annots[0]
                # Determine field type: walk up to find /FT
                ft_owner = primary
                while ft_owner is not None and ft_owner.FT is None:
                    ft_owner = ft_owner.Parent
                ft = ft_owner.FT if ft_owner is not None else None
                ff = 0
                ff_owner = primary
                while ff_owner is not None:
                    if ff_owner.Ff is not None:
                        ff = int(ff_owner.Ff)
                        break
                    ff_owner = ff_owner.Parent

                if ft == PdfName("Tx"):
                    for a in annots:
                        a.update(PdfDict(V=PdfString.encode(str(raw_value)), AP=None))
                    # Also update the parent field if any
                    if ft_owner is not None and ft_owner is not primary:
                        ft_owner.update(PdfDict(V=PdfString.encode(str(raw_value))))
                    filled.append(name)
                elif ft == PdfName("Btn"):
                    is_radio = bool(ff & (1 << 15))
                    is_push = bool(ff & (1 << 16))
                    if is_push:
                        failed.append(name); continue
                    if is_radio:
                        opt = str(raw_value).lstrip("/")
                        if ft_owner is not None:
                            ft_owner.V = PdfName(opt)
                        for kid in annots:
                            ap_n = (kid.AP or PdfDict()).N or PdfDict()
                            keys = [str(k).lstrip("/") for k in ap_n.keys()]
                            kid.AS = PdfName(opt) if opt in keys else PdfName("Off")
                        filled.append(name)
                    else:
                        # checkbox: pick on value from /AP/N
                        on = "Yes"
                        ap_n = (primary.AP or PdfDict()).N or PdfDict()
                        for k in ap_n.keys():
                            ks = str(k).lstrip("/")
                            if ks != "Off":
                                on = ks; break
                        state = on if coerce_checkbox(raw_value) else "Off"
                        for a in annots:
                            a.V = PdfName(state)
                            a.AS = PdfName(state)
                        if ft_owner is not None and ft_owner is not primary:
                            ft_owner.V = PdfName(state)
                        filled.append(name)
                elif ft == PdfName("Ch"):
                    for a in annots:
                        a.V = PdfString.encode(str(raw_value))
                    if ft_owner is not None and ft_owner is not primary:
                        ft_owner.V = PdfString.encode(str(raw_value))
                    filled.append(name)
                else:
                    failed.append(name)
            except Exception:
                failed.append(name)

        try:
            PdfWriter().write(str(output_path), tpl)
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
