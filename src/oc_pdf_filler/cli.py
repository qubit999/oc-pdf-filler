"""Command-line interface for oc-pdf-filler."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .extract import extract_to_dict
from .fill import fill_pdf, available_backends
from .backends import DEFAULT_ORDER


_WORKSPACE_ENV_VARS = (
    "OC_PDF_FILLER_WORKSPACE",
    "OPENCLAW_WORKSPACE",
    "CLAWHUB_WORKSPACE",
    "AGENT_WORKSPACE",
    "SKILL_WORKSPACE",
    "WORKSPACE",
)


def _resolve_workspace(explicit: str | None) -> Path:
    """Pick the directory all artifacts must stay inside."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    for var in _WORKSPACE_ENV_VARS:
        val = os.environ.get(var)
        if val:
            return Path(val).expanduser().resolve()
    return Path.cwd().resolve()


def _confine_to_workspace(path: str | Path, workspace: Path, default_name: str) -> Path:
    """Resolve `path` so the result is always inside `workspace`.

    Relative paths join the workspace; absolute paths outside the workspace
    are rewritten to use just their basename inside the workspace, so the
    agent host's sandbox doesn't reject the artifact.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    p = Path(path).expanduser() if path else Path(default_name)
    if not p.is_absolute():
        p = workspace / p
    p = p.resolve()
    try:
        p.relative_to(workspace)
        return p
    except ValueError:
        rerouted = (workspace / (p.name or default_name)).resolve()
        sys.stderr.write(
            f"warning: '{p}' is outside the workspace ({workspace}); "
            f"writing to '{rerouted}' instead.\n"
        )
        return rerouted


def _cmd_extract(args: argparse.Namespace) -> int:
    data = extract_to_dict(args.pdf)
    if not args.include_values:
        for f in data["fields"]:
            f.pop("value", None)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if args.output:
        workspace = _resolve_workspace(args.workspace)
        default_name = f"{Path(args.pdf).stem}_schema.json"
        out = _confine_to_workspace(args.output, workspace, default_name)
        out.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


def _cmd_fill(args: argparse.Namespace) -> int:
    values = json.loads(Path(args.values).read_text(encoding="utf-8"))
    if not isinstance(values, dict):
        print("error: values JSON must be an object {field: value}", file=sys.stderr)
        return 2

    workspace = _resolve_workspace(args.workspace)
    src = Path(args.pdf)
    default_name = f"{src.stem}_done{src.suffix or '.pdf'}"
    output = _confine_to_workspace(args.output, workspace, default_name)

    schema = extract_to_dict(str(src))
    checkbox_names = [f["name"] for f in schema["fields"] if f["type"] == "checkbox"]
    radio_fields = [f for f in schema["fields"] if f["type"] == "radio"]
    radio_names = [f["name"] for f in radio_fields]
    unset_checkboxes = [n for n in checkbox_names if n not in values]
    unset_radios = [n for n in radio_names if n not in values]

    if args.default_unset_checkboxes != "skip":
        default_value = args.default_unset_checkboxes == "on"
        for name in unset_checkboxes:
            values[name] = default_value

    if args.default_unset_radios == "first":
        for f in radio_fields:
            if f["name"] in values:
                continue
            options = f.get("options") or []
            if options:
                values[f["name"]] = options[0]

    final, attempts = fill_pdf(
        args.pdf,
        values,
        str(output),
        backend=args.backend,
        flatten=args.flatten,
        best_effort=args.best_effort,
    )

    summary = {
        "winning_backend": final.backend,
        "success": final.success,
        "workspace": str(workspace),
        "output_path": str(output),
        "filled": final.filled_fields,
        "missing": final.missing_fields,
        "failed": final.failed_fields,
        "unset_checkboxes": unset_checkboxes,
        "unset_radios": unset_radios,
        "default_unset_checkboxes": args.default_unset_checkboxes,
        "default_unset_radios": args.default_unset_radios,
        "error": final.error,
        "attempts": [a.to_dict() for a in attempts],
    }

    if unset_checkboxes and args.default_unset_checkboxes == "skip":
        sys.stderr.write(
            f"warning: {len(unset_checkboxes)} checkbox field(s) were not in your "
            f"values JSON and were left untouched: {', '.join(unset_checkboxes[:8])}"
            f"{' ...' if len(unset_checkboxes) > 8 else ''}\n"
            f"Pass --default-unset-checkboxes off to force them to false, or include "
            f"them explicitly in the values file.\n"
        )

    if unset_radios and args.default_unset_radios == "skip":
        sys.stderr.write(
            f"warning: {len(unset_radios)} radio field(s) were not in your values "
            f"JSON and were left untouched: {', '.join(unset_radios[:8])}"
            f"{' ...' if len(unset_radios) > 8 else ''}\n"
            f"Pass --default-unset-radios first to pick the first available option "
            f"for each, or include them explicitly in the values file.\n"
        )

    if args.strict and (final.missing_fields or final.failed_fields or not final.success):
        print(json.dumps(summary, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2))
    return 0 if final.success else 1


def _cmd_list_backends(args: argparse.Namespace) -> int:
    out = []
    for b in DEFAULT_ORDER:
        out.append({"name": b.name, "available": b.available()})
    print(json.dumps({"order": out, "available": available_backends()}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="oc-pdf-filler", description=__doc__)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--workspace",
        help=(
            "Directory all output artifacts must stay inside. "
            "Defaults to $OC_PDF_FILLER_WORKSPACE / $OPENCLAW_WORKSPACE / "
            "$CLAWHUB_WORKSPACE / $AGENT_WORKSPACE / $SKILL_WORKSPACE / "
            "$WORKSPACE, or the current directory."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("extract", help="Extract field schema from a PDF.")
    pe.add_argument("pdf")
    pe.add_argument("-o", "--output", help="Write JSON to file instead of stdout.")
    pe.add_argument("--include-values", action="store_true",
                    help="Include current /V values in the output.")
    pe.set_defaults(func=_cmd_extract)

    pf = sub.add_parser("fill", help="Fill a PDF with values from a JSON file.")
    pf.add_argument("pdf")
    pf.add_argument("values", help="JSON file: {field_name: value}")
    pf.add_argument("-o", "--output",
                    help=(
                        "Output PDF path. Resolved relative to the workspace; "
                        "defaults to <input-stem>_done.pdf inside the workspace."
                    ))
    pf.add_argument("--backend", default="auto",
                    choices=["auto"] + [b.name for b in DEFAULT_ORDER])
    pf.add_argument("--flatten", action="store_true")
    pf.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any field is missing or fails.")
    pf.add_argument("--best-effort", action="store_true",
                    help="Chain backends so partial fills accumulate.")
    pf.add_argument("--default-unset-checkboxes",
                    choices=["off", "on", "skip"], default="skip",
                    help=(
                        "How to handle checkbox fields not present in the values "
                        "JSON. 'off' (recommended) sets them to false, 'on' to "
                        "true, 'skip' (default) leaves them as-is."
                    ))
    pf.add_argument("--default-unset-radios",
                    choices=["first", "skip"], default="skip",
                    help=(
                        "How to handle radio fields not present in the values "
                        "JSON. 'first' picks the first available option for each, "
                        "'skip' (default) leaves them as-is."
                    ))
    pf.set_defaults(func=_cmd_fill)

    pb = sub.add_parser("list-backends", help="List installed backends.")
    pb.set_defaults(func=_cmd_list_backends)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
