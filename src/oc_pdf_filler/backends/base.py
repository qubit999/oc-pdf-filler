"""Abstract base class for fill backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import FillResult


class FillBackend(ABC):
    name: str = "base"

    @classmethod
    @abstractmethod
    def available(cls) -> bool:
        """Return True if this backend's runtime dependencies are present."""

    @abstractmethod
    def fill(
        self,
        input_path: str | Path,
        values: dict[str, Any],
        output_path: str | Path,
        *,
        flatten: bool = False,
    ) -> FillResult:
        """Fill input PDF form fields with values, write to output_path."""


def coerce_checkbox(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on", "x", "y", "checked"}
    return bool(value)
