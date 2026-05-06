"""pdftk CLI fill backend (last-resort, requires the `pdftk` binary)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..models import FillResult
from .base import FillBackend, coerce_checkbox


def _fdf_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def _build_fdf(values: dict[str, Any]) -> bytes:
    parts = [b"%FDF-1.2\n", b"1 0 obj\n<< /FDF << /Fields ["]
    body: list[str] = []
    for name, val in values.items():
        if isinstance(val, bool):
            v = "Yes" if val else "Off"
            body.append(f"<< /T ({_fdf_escape(name)}) /V /{v} >>")
        else:
            body.append(f"<< /T ({_fdf_escape(name)}) /V ({_fdf_escape(str(val))}) >>")
    parts.append("\n".join(body).encode("utf-8"))
    parts.append(b"] >> >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n")
    return b"".join(parts)


class PdftkBackend(FillBackend):
    name = "pdftk"

    @classmethod
    def available(cls) -> bool:
        return shutil.which("pdftk") is not None

    def fill(self, input_path, values, output_path, *, flatten=False) -> FillResult:
        if not self.available():
            return FillResult(self.name, False, error="pdftk binary not found on PATH")

        with tempfile.NamedTemporaryFile(suffix=".fdf", delete=False) as tf:
            tf.write(_build_fdf(values))
            fdf_path = tf.name

        cmd = [
            "pdftk", str(input_path),
            "fill_form", fdf_path,
            "output", str(output_path),
        ]
        if flatten:
            cmd.append("flatten")

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        finally:
            Path(fdf_path).unlink(missing_ok=True)

        if proc.returncode != 0:
            return FillResult(
                self.name, False,
                error=f"pdftk exit {proc.returncode}: {proc.stderr.strip()}",
            )

        # pdftk doesn't tell us which fields it actually set; assume all keys filled.
        return FillResult(
            backend=self.name,
            success=True,
            filled_fields=list(values.keys()),
        )
