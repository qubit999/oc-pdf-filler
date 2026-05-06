"""Command-line interface for oc-pdf-filler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .extract import extract_to_dict
from .fill import fill_pdf, available_backends
from .backends import DEFAULT_ORDER


def _cmd_extract(args: argparse.Namespace) -> int:
    data = extract_to_dict(args.pdf)
    if not args.include_values:
        for f in data["fields"]:
            f.pop("value", None)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


def _cmd_fill(args: argparse.Namespace) -> int:
    values = json.loads(Path(args.values).read_text(encoding="utf-8"))
    if not isinstance(values, dict):
        print("error: values JSON must be an object {field: value}", file=sys.stderr)
        return 2

    output = args.output
    if not output:
        src = Path(args.pdf)
        output = str(Path.cwd() / f"{src.stem}_done{src.suffix or '.pdf'}")

    final, attempts = fill_pdf(
        args.pdf,
        values,
        output,
        backend=args.backend,
        flatten=args.flatten,
        best_effort=args.best_effort,
    )

    summary = {
        "winning_backend": final.backend,
        "success": final.success,
        "output_path": str(Path(output).resolve()),
        "filled": final.filled_fields,
        "missing": final.missing_fields,
        "failed": final.failed_fields,
        "error": final.error,
        "attempts": [a.to_dict() for a in attempts],
    }

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
                    help="Output PDF path. Defaults to ./<input-stem>_done.pdf in cwd.")
    pf.add_argument("--backend", default="auto",
                    choices=["auto"] + [b.name for b in DEFAULT_ORDER])
    pf.add_argument("--flatten", action="store_true")
    pf.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any field is missing or fails.")
    pf.add_argument("--best-effort", action="store_true",
                    help="Chain backends so partial fills accumulate.")
    pf.set_defaults(func=_cmd_fill)

    pb = sub.add_parser("list-backends", help="List installed backends.")
    pb.set_defaults(func=_cmd_list_backends)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
