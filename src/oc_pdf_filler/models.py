"""Field metadata and result types shared by all backends."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class FieldType(str, Enum):
    TEXT = "text"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    CHOICE = "choice"
    SIGNATURE = "signature"
    PUSHBUTTON = "pushbutton"
    UNKNOWN = "unknown"


@dataclass
class FieldInfo:
    name: str
    type: FieldType
    page: int | None = None
    value: Any = None
    options: list[str] = field(default_factory=list)
    max_length: int | None = None
    required: bool = False
    multiline: bool = False
    read_only: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d


@dataclass
class FillResult:
    backend: str
    success: bool
    filled_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    failed_fields: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
