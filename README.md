# oc-pdf-filler

Extract and fill PDF AcroForm fields from the command line, with a multi-backend fallback chain so a single quirky PDF doesn't block your workflow.

The repo ships **two artifacts**:

1. A Python package and CLI: `oc-pdf-filler` (subcommands: `extract`, `fill`, `list-backends`).
2. An [OpenClaw](https://docs.openclaw.ai) / [AgentSkills](https://agentskills.io) skill at `skills/pdf-filler/` that wraps the CLI so agents can use it.

## Why a fallback chain?

PDF AcroForms are notoriously inconsistent. The orchestrator tries each backend in order and stops at the first one that fills every requested field:

1. **pypdf** -- pure Python, required dependency.
2. **pdfrw** -- fine-grained dictionary control (optional).
3. **PyMuPDF** -- robust appearance regeneration, native checkbox/radio handling (optional).
4. **pdftk** -- system binary, last resort (optional).

Backends without their dependency present are skipped automatically.

## Install

```bash
pip install -e ".[all]"          # full fallback chain (pypdf + pdfrw + PyMuPDF)
# or, minimal:
pip install -e .                 # pypdf only
# Optional system dep:
brew install pdftk-java          # macOS
apt install pdftk-java           # Debian/Ubuntu
```

Verify your backends:

```bash
oc-pdf-filler list-backends
```

## CLI usage

### Extract a field schema

```bash
oc-pdf-filler extract form.pdf --output schema.json --include-values
```

Output is JSON with one entry per field:

```json
{
  "field_count": 27,
  "fields": [
    {
      "name": "Name Verantwortlicher",
      "type": "text",
      "value": "ACME GmbH",
      "options": [],
      "max_length": null,
      "required": false,
      "multiline": false,
      "read_only": false
    }
  ]
}
```

`type` is one of `text`, `checkbox`, `radio`, `choice`, `signature`, `pushbutton`, `unknown`.

### Fill a PDF

Build a JSON values file. Field names come from the schema verbatim.

```json
{
  "Name Verantwortlicher": "ACME GmbH",
  "Postleitzahl Verantwortlicher": "10115",
  "Beschäftigte": true,
  "Verarbeitungstyp": "Automatisiert"
}
```

Then run:

```bash
oc-pdf-filler fill form.pdf values.json --output filled.pdf
```

Useful flags:

| Flag             | Effect                                                                |
|------------------|-----------------------------------------------------------------------|
| `--backend NAME` | Force one of `pypdf` / `pdfrw` / `pymupdf` / `pdftk` (default: auto)  |
| `--best-effort`  | Chain backends so partial fills accumulate                            |
| `--flatten`      | Bake values into the PDF (best support: PyMuPDF, pdftk)               |
| `--strict`       | Exit non-zero if any field is missing or unfillable                   |

### Value coercion per field type

| Type        | JSON value                                                                 |
|-------------|----------------------------------------------------------------------------|
| `text`      | string (newlines preserved when `multiline` is true)                       |
| `checkbox`  | `true` / `false` or `"true"`, `"yes"`, `"on"`, `"x"`, `"1"`, `"checked"`   |
| `radio`     | string equal to one of the entries in the field's `options` array          |
| `choice`    | string equal to one of the dropdown options                                |
| `signature` | not supported -- reported in the schema, ignored at fill time              |

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

Tests run against the three real PDFs in `test_pdfs/` and parametrize across every available backend. They round-trip text and checkbox values (fill, re-extract, assert).

## OpenClaw skill

The `skills/pdf-filler/` folder is an [AgentSkills.io spec](https://agentskills.io/specification.md)-compliant skill that an OpenClaw agent can load to get PDF-filling capabilities. It contains:

```
skills/pdf-filler/
├── SKILL.md                    # frontmatter + instructions
├── scripts/
│   ├── extract.py
│   ├── fill.py
│   └── list_backends.py
├── references/
│   ├── FIELD_TYPES.md
│   └── BACKENDS.md
└── assets/
    └── values.example.json
```

Validate it:

```bash
npx skills-ref validate ./skills/pdf-filler
```

### Releasing a new version

Bump `metadata.version` in `skills/pdf-filler/SKILL.md`, then run:

```bash
clawhub publish ./skills/pdf-filler --version <semver>
```

`--version` is required and must be valid semver, and should match `metadata.version` so the registry record stays in sync.

The agent that loads the skill needs `oc-pdf-filler` installed in its workspace Python environment for the scripts to run; the skill's `compatibility` field documents this.

## License

MIT
