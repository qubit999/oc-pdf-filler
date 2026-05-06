"""Fill orchestrator: try each backend in order until one fully succeeds."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

from .backends import DEFAULT_ORDER, FillBackend
from .models import FillResult


def available_backends() -> list[str]:
    return [b.name for b in DEFAULT_ORDER if b.available()]


def _resolve_order(preferred: str | None) -> list[type[FillBackend]]:
    if preferred is None or preferred == "auto":
        return [b for b in DEFAULT_ORDER if b.available()]
    for b in DEFAULT_ORDER:
        if b.name == preferred:
            if not b.available():
                raise RuntimeError(f"Backend '{preferred}' is not available on this system.")
            return [b]
    raise ValueError(f"Unknown backend '{preferred}'.")


def fill_pdf(
    input_path: str | Path,
    values: dict[str, Any],
    output_path: str | Path,
    *,
    backend: str | None = "auto",
    flatten: bool = False,
    best_effort: bool = False,
) -> tuple[FillResult, list[FillResult]]:
    """Fill ``input_path`` with ``values`` using the configured fallback chain.

    Returns ``(winning_result, all_attempts)``. If no backend succeeds fully and
    ``best_effort`` is False, the last attempt is returned with success=False.
    With ``best_effort=True``, the orchestrator chains backends, feeding each
    backend's output into the next backend so partial fills accumulate.
    """
    order = _resolve_order(backend)
    if not order:
        result = FillResult("none", False, error="no backends available")
        return result, [result]

    attempts: list[FillResult] = []

    if not best_effort:
        for cls in order:
            res = cls().fill(input_path, values, output_path, flatten=flatten)
            attempts.append(res)
            if res.success:
                return res, attempts
        return attempts[-1], attempts

    # best_effort: chain backends, accumulating filled fields
    remaining = dict(values)
    current_input = Path(input_path)
    tmpdir = Path(tempfile.mkdtemp(prefix="ocpdf-"))
    all_filled: list[str] = []
    last_res: FillResult | None = None
    try:
        for i, cls in enumerate(order):
            if not remaining:
                break
            target = Path(output_path) if i == len(order) - 1 else tmpdir / f"step{i}.pdf"
            res = cls().fill(current_input, remaining, target, flatten=flatten)
            attempts.append(res)
            for f in res.filled_fields:
                if f in remaining:
                    remaining.pop(f)
                    all_filled.append(f)
            last_res = res
            if target.exists():
                current_input = target
            if not remaining:
                if current_input != Path(output_path):
                    shutil.copyfile(current_input, output_path)
                break
        if Path(output_path).exists() is False and current_input.exists():
            shutil.copyfile(current_input, output_path)
    finally:
        # keep tmpdir for debugging? No, clean up.
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    final = FillResult(
        backend="+".join(a.backend for a in attempts),
        success=not remaining,
        filled_fields=all_filled,
        missing_fields=list(remaining.keys()),
        failed_fields=[],
        error=None if not remaining else f"{len(remaining)} field(s) unfilled",
    )
    return final, attempts
