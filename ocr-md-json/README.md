# ocr-md-json — consolidate scanned/native documents to Markdown + JSON (verified)

An **agent-preset package** for DSH. Sessions started on the **OCR-MD-JSON**
preset turn a folder of mixed source documents — native digital PDFs, scanned
image PDFs, and photos — into ONE sanitized **Consolidated Markdown record** plus
a **JSON of every table** in it, with deterministic extraction and an optional
independent second-pass verification.

This is the agent-driven pipeline: it uses **DSH's own tools** (filesystem,
`read_image` vision, background subagents, shell), not a separate local OCR
engine. It is intentionally different from the `ocr-md` preset, which drives a
local Ollama model ladder through a runner script.

```
  source folder (PDFs, images, TXT)
        │
        ├─ native PDFs ──► embedded text layer (deterministic, lossless)
        ├─ scanned PDFs ─► page images extracted  ─┐
        ├─ photos ────────► hash-deduplicated      ├─► vision read (subagents) ─┐
        │                                          └────────────────────────────┤
        ▼                                                                        ▼
  2-Pass verification (optional)──────────────► Consolidated .md  +  .json tables
```

## Files

| File | Purpose |
|---|---|
| `preset.yml` | Display name/description for preset pickers |
| `agent.cordis.yml` | Composition: OCR-MD-JSON persona + the DSH tool rows it needs |
| `skills/ocr-md-json/SKILL.md` | The full workflow instructions (the actual "how-to") |
| `scripts/extract_pdf_text.py` | Embedded PDF text extraction (zlib + ToUnicode CMap), no OCR |
| `scripts/extract_pdf_images.py` | Page-image extraction from scanned/image PDFs |
| `scripts/dedupe.py` | Hash-based duplicate detection across a folder |
| `scripts/md_tables_to_json.py` | Parse any Markdown tables into a structured JSON file |
| `docs/consolidated-record.TEMPLATE.md` | Sanitized layout of the consolidated output record |
| `README.md` | This file |

## Install

```
Copy-Item -Recurse ocr-md-json "$env:USERPROFILE\.dsh\.agent-presets\"
```

Start a session on the **OCR-MD-JSON** preset. Then ask, e.g.:

> "consolidate the files in `Z:\docs\year` into one record and give me the JSON."

The agent:
1. inspects the folder (extension/count/sizes) and **stages a copy into the workspace** so its own tools can process it (reads/writes are then all inside the session workspace).
2. For each **native PDF**, extracts the embedded text layer directly (the script below) — this is *not* OCR, so it is essentially instant and exact.
3. For each **scanned PDF / photo**, rasterizes/extracts the page images and **hash-deduplicates** them, then reads the distinct ones with the model's vision (parallel background subagents) to transcribe labelled values.
4. **Consolidates** everything into one Markdown record (patient block, imaging, labs, docs, source index) and, on request, auto-generates the **JSON of the MD tables**.
5. Optionally runs a **2-Pass** verification: fresh-context re-reads of flagged values, producing a `2-Pass` record with a Verification table (Pass 1 | Pass 2 | Verdict | Confidence).

## Which LLM model was used

This preset's orchestration and all vision reading run on **DSH's own agent
route** — the session model that started the workflow, which for the sessions
that produced this preset was **`deepseek-v4-flash-vision-exp`**.

| Work | Model |
|---|---|
| Step 2 — native-PDF text extraction | **deterministic** (no model) — zlib + PDF font CMap |
| Step 3 — vision reading of scans/photos | `deepseek-v4-flash-vision-exp` (accepts text **and** image) via DSH `read_image`, run in parallel background subagents |
| Step 4/5 — consolidation, JSON, verification notes | `deepseek-v4-flash-vision-exp` (same agent route) |
| Step 5 2-Pass verification | fresh-context subagents on the **same** model route (independent context, same model family) |

- The vision model accepts image input (`read_image`), so no separate OCR engine
  is required.
- `deepseek-v4-flash-vision-exp` has a 1M context window and supports
  `reasoning`; it was used for both text and image turns.
- Because verification subagents share the same model, the 2-Pass check is an
  *independent fresh read*, not a different vendor. To get a true cross-provider
  cross-check, route the pass-2 subagents to a different registered vision model
  (see `agent.cordis.yml` / `SKILL.md`). No model override is applied here by
  default.

> Note for reproducibility: "the model used" is whatever DSH route the session
> is on, not a value baked into the preset. The scripts themselves are model-free.

## Sanitization statement

This package is a **template**: it contains no patient names, identifiers
(NRIC/DOB/MRN), hospital names, or clinical values. Every script takes generic
input paths and the record template uses `<PLACEHOLDER>` fields. When you run
it, keep source files on disk and avoid pasting private values into the
conversation beyond what is necessary — the pipeline writes outputs **to disk**,
not into the chat.

Still, a preset carries shell-level trust by design: it runs local processes and
writes files. Only distribute this folder through channels you trust.

## Scripts (generic, no PHI)

```powershell
# native PDF -> text
py scripts\extract_pdf_text.py "C:\docs\report.pdf"        # prints to stdout, or
py scripts\extract_pdf_text.py "C:\docs\report.pdf" -o out.txt

# scanned/image PDF -> page images
py scripts\extract_pdf_images.py "C:\docs\scan.pdf" -out "C:\docs\pages"

# hash-deduplicate a folder
py scripts\dedupe.py "C:\docs"

# Markdown tables -> JSON
py scripts\md_tables_to_json.py "C:\out\record.md" -o "C:\out\tables.json"
```

> Python requirement: the extraction scripts use **only the standard library**
> (`zlib`, `re`, `zipfile`-free, `hashlib`) plus `Pillow` for image output
> (`py -m pip install --user pillow`). No `pypdf`, no OCR libraries needed.

## Key difference vs `ocr-md`

| | `ocr-md` | `ocr-md-json` |
|---|---|---|
| Perception | local Ollama ladder (glm-ocr etc.) via `ocr.ps1` | DSH `read_image` vision + embedded-PDF text extraction |
| Runner | deterministic PowerShell pipeline, two passes + judge | agent-orchestrated, subagent fan-out, optional 2-Pass |
| Output | `<name>.ocr.md` + `.manifest.json` + `.extract.json` | `*Consolidated.md` + `*Tables.json` (+ optional `2-Pass *`) |
| Data egress | local-first, cloud tier off by default | no cloud key used; follows DSH model route |

Choose `ocr-md` when you want byte-per-repetition determinism and local-only
models; choose `ocr-md-json` when you already have a curated folder and want one
consolidated record plus its tables, fast, using the session's own model.

## Troubleshooting

- **`read_image` not in the catalog** — the vision tool is mounted on the
  vision-capable model route, not the plain-text route. Start the session on a
  model that accepts image input (see the model table above).
- **Pip installs blocked for `pypdf`/OCR libs** — this preset does not need them.
  The PDF scripts use the stdlib + `Pillow` only.
- **Duplicates getting re-transcribed** — run `dedupe.py` first; many photo
  exports are the same page re-saved under several names (a common cause).
- **Values disagree between a native PDF and its photo** — that indicates the
  scan is a *re-print* of the same report; prefer the deterministic native-PDF
  text and flag the discrepancy rather than treating them as two facts.
- **Model override for a true cross-provider 2-Pass** — set a different vision
  provider/model on the pass-2 subagents (see `SKILL.md`).
