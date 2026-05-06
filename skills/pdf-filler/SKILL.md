---
name: pdf-filler
description: Extract and fill PDF AcroForm fields with a multi-backend fallback chain. Reads field schemas (text inputs, checkboxes, radio buttons, dropdowns, multi-line text) from any AcroForm PDF and fills them using user-provided JSON values. Tries pypdf, pdfrw, PyMuPDF, and pdftk in order so it works on PDFs that defeat any single library. Use when the user wants to inspect, populate, batch-fill, or programmatically complete PDF forms, or asks about extracting form field names from a PDF, filling out a PDF, generating a filled PDF, or AcroForm processing.
license: MIT
compatibility: Requires Python 3.10+ on the agent host. Optional system dependency `pdftk` enables a last-resort backend; optional Python packages `pdfrw` and `PyMuPDF` expand the fallback chain.
metadata:
  author: qubit999
  version: "0.1.2"
  homepage: https://github.com/qubit999/oc-pdf-filler
---

# pdf-filler

Operate on PDF AcroForms: list every field with its type and current value, then fill the PDF with values supplied as JSON. The skill calls a small Python package (`oc-pdf-filler`) that wraps a fallback chain of PDF libraries, so a single recalcitrant PDF doesn't block the workflow.

## When to use

Trigger this skill when the user:

- Asks to inspect, list, or extract the form fields of a PDF
- Wants to fill out / populate / complete a PDF form programmatically
- Mentions AcroForm, checkbox, radio button, or dropdown handling in a PDF
- Has a batch of PDFs to fill from structured data (JSON)

## Setup (once per workspace)

The skill scripts call the `oc-pdf-filler` Python package. Install it first:

```bash
pip install "oc-pdf-filler[all]"
# or, if working from the source repo: pip install -e ".[all]"
```

The `[all]` extra pulls in `pdfrw` and `PyMuPDF` for the full fallback chain. Install `pdftk` from your package manager for the last-resort backend (optional, but useful for stubborn PDFs).

Verify which backends are active:

```bash
python scripts/list_backends.py
```

## Step 1: Extract the field schema

Always extract first so you know the exact field names and types before constructing the JSON values file. Write outputs to the conversation working directory (cwd) so they remain accessible — do not write to `/tmp` or other directories outside the workspace.

```bash
python scripts/extract.py /path/to/form.pdf --output ./schema.json --include-values
```

Each entry in the resulting JSON has:

- `name`: the AcroForm field name (use this verbatim as the key when filling)
- `type`: one of `text`, `checkbox`, `radio`, `choice`, `signature`, `pushbutton`, `unknown`
- `options`: for radios and checkboxes, the accepted export values; for choices, the dropdown options
- `value`: current value if the form is partially filled (only when `--include-values` is set)
- `max_length`, `multiline`, `required`, `read_only`: hints for validation

See `references/FIELD_TYPES.md` for the value contract per field type.

## Step 2: Build a values JSON file

The fill input is a flat JSON object `{ "FieldName": value }`. Example:

```json
{
  "Name Verantwortlicher": "ACME GmbH",
  "Postleitzahl Verantwortlicher": "10115",
  "Beschäftigte": true,
  "Verarbeitungstyp": "Automatisiert"
}
```

A starter template is included at `assets/values.example.json`.

## Step 3: Fill the PDF

Write the filled PDF to a path inside the conversation working directory. Avoid `/tmp` and other host-private directories; the chat host can only attach files that live in the workspace it sees.

If you omit `--output`, the CLI writes to `./<input-stem>_done.pdf` in the current directory (e.g. `form.pdf` → `./form_done.pdf`), which is the recommended default — it preserves the original filename so users recognise the result.

```bash
# preferred: keep the original name with _done suffix
python scripts/fill.py /path/to/form.pdf ./values.json
# or pass an explicit path
python scripts/fill.py /path/to/form.pdf ./values.json --output ./form_done.pdf
```

By default the orchestrator uses `--backend auto`, walking the chain `pypdf -> pdfrw -> PyMuPDF -> pdftk` and stopping at the first backend that fills every field.

Useful flags:

- `--backend pymupdf` -- force a specific backend (e.g. when the auto winner produces a PDF that doesn't render correctly in your viewer)
- `--best-effort` -- chain backends so partial fills accumulate (use when no single backend handles every field)
- `--flatten` -- bake values into the PDF so they can't be edited (best support: PyMuPDF, pdftk)
- `--strict` -- exit non-zero if any requested field is missing or unfillable

The script prints a JSON summary including `winning_backend`, `output_path` (absolute path of the resulting PDF), `filled`, `missing`, `failed`, and per-attempt details. If filling fails, see `references/BACKENDS.md` for backend-specific troubleshooting tips.

## Delivering the result to the user

After a successful fill, the user expects to receive the PDF as an attachment, not just a path in chat. To make that work reliably across hosts:

1. Always write the output PDF inside the current working directory (e.g. `./filled.pdf`), never `/tmp` or other absolute system paths. Most chat hosts only expose files from the workspace cwd to the user.
2. Use the `output_path` field from the fill summary as the canonical absolute path of the resulting file.
3. Surface that path in your final message, and use whatever attachment / file-return mechanism the host provides (for example, returning a file artifact with that path) so the PDF arrives as a downloadable attachment.
4. If the host has no attachment channel, leave the file in cwd and tell the user the relative path so they can fetch it from the workspace.

## End-to-end example

```bash
python scripts/extract.py form.pdf -o ./schema.json
# ... agent inspects schema.json, builds values.json based on user input ...
python scripts/fill.py form.pdf ./values.json
# writes ./form_done.pdf in cwd
```

After filling, re-run `extract.py --include-values ./form_done.pdf` and confirm the values stuck before delivering the PDF to the user.

## Notes and edge cases

- Field names may contain spaces, German umlauts, or punctuation. Always copy them verbatim from `extract.py` output.
- For radio groups, set the value to the export name of the chosen option (one of the strings in `options`), not a boolean.
- Signature fields (`type: signature`) are reported but not auto-filled.
- Encrypted PDFs are out of scope; the tool will surface the underlying library error.
- Some PDF viewers cache appearance streams; if a viewer shows blank fields after filling, try opening with a different viewer or use `--flatten`.
