# OCR-MD-JSON

Consolidate a source folder of **native PDFs, scanned/image PDFs, and photos**
into **one Markdown record + a JSON of every table in it**, with deterministic
text extraction, hash dedup, parallel vision subagents, and an optional
independent 2-Pass verification.

This skill is the concrete checklist the agent follows when the user asks to
"consolidate a folder into one record (and JSON)". It complements the persona in
`agent.cordis.yml`; run its steps in order and report what you did.

## When to use

Use this for a curated folder of mixed documents you want merged into a single
readable record + structured tables. Use the `ocr-md` (local Ollama) preset
instead when you need local-only, byte-reproducible per-file transcription and
do not want to rely on the session model's vision.

## The pipeline

```
source folder
  ├─ .txt / .csv ─────────────────────► read directly
  ├─ native PDF (has text layer) ────► extract_pdf_text.py  (no model; exact)
  └─ scanned PDF / image ────────────► extract_pdf_images.py ─► dedupe.py
                                              └► vision subagents (read_image)
        ▼
 consolidated .md  +  md_tables_to_json.py ─► *.json
        ▼
 optional: 2-Pass verification -> "2-Pass <record>.md" (Verification table)
```

## Steps

### 1. Inspect and stage
- List the folder: extensions, count, sizes. Note any duplicate-looking sizes.
- **Copy the whole folder into the session workspace** so every read/write stays
  inside the sandbox you actually have (reads of network/other drives may be
  blocked, but once copied to the workspace the tools work normally).

### 2. Classify each file
- `.txt` / `.csv` → read with the `read` tool.
- **Native PDF** → try `extract_pdf_text.py`.
- **Scanned/image PDF or photo** → extract page images, then dedupe.

### 3. Embedded text extraction (native PDFs) — the fast, exact path
```powershell
py "%USERPROFILE%\.dsh\.agent-presets\ocr-md-json\scripts\extract_pdf_text.py" "C:\...\report.pdf" -o out.txt
```
- The script zlib-decompresses the content streams and maps each `<hex> Tj`
  glyph code through the font's `ToUnicode` CMap.
- **Verify it worked:** exam/account/ID numbers must stay intact. If you see
  `00520061...` garbage, the returned text is double-encoded — apply a cleanup
  that collapses `00XX` → byte and re-check the numbers.
- If the text layer is empty (some PDFs are image-only), fall back to step 4.

### 4. Page-image extraction (scanned/image PDFs) + dedup
```powershell
py "...\scripts\extract_pdf_images.py" "C:\...\scan.pdf" -out "C:\...\pages"
py "...\scripts\dedupe.py" "C:\...\pages"      # list identical files
```
- Only transcribe **unique** images. Photo exports are often the same page saved
  under several names (this alone removes ~40% of a typical medical-photo dump).

### 5. Vision read — parallel background subagents
- Group the distinct images **by document** (not one subagent per image).
- Give each subagent a self-contained prompt with the **exact absolute file
  paths**, tell it to use `read_image`, and to return clean Markdown (a heading
  per file + a table of `test | value | unit | ref range | flag`).
- Tell it explicitly: if a value is illegible/rotated/handwritten, mark it and
  do **not** guess.
- Run them **all in the background** in one message; collect each result as they
  settle. Use `list_agents` to watch, never poll in a loop.

### 6. Consolidate into ONE Markdown record
Structure:
1. **Title** + a provenance line (`Record built from: <source dir>`).
2. **Patient / subject identification** (placeholders, not raw private IDs in
   templates).
3. **Imaging/radiology** — chronological, one subsection per study, with
   findings + impression.
4. **Laboratory results** — chronological, tabular, with reference ranges and
   flags.
5. **Scanned clinical documents** — referral letters, discharge notes, meds.
6. **Administrative documents** — separator, brief.
7. **Source files index** — `source file | type | content`.

Rules:
- **Never alter a value.** Cross-check repeated fields (same study across years,
  repeated MRN/DOB) and **note** any discrepancy rather than resolving it.
- Group a study that appears in multiple years once and cross-reference it.

### 7. JSON of the record's tables
```powershell
py "...\scripts\md_tables_to_json.py" "C:\...\Consolidated.md" -o "C:\...\Tables.json"
```
- Schema: `{"title":..., "table_count":N, "tables":[{"name","title","headers","rows":[{col:val}]}]}`.

### 8. Optional 2-Pass verification
For clinical/financial values, run a verification pass:
- Re-run fresh-context subagents that **re-read the flagged/unclear images** and
  return `{id, value, confidence, note}`.
- Reconcile each against pass 1: **confirmed** / **corrected** / **unresolved**.
- Emit `2-Pass <record>.md` that leads with a **Verification table**
  (`Field | Pass 1 | Pass 2 | Verdict | Confidence`) and update corrected values
  inline with a `(pass-2 corrected ...)` note.
- **Do not silently pick a side** on a genuinely ambiguous value; mark it
  `unresolved` and state why.
- To get a true **cross-provider** check (not just a fresh read), set a different
  registered vision provider/model on the pass-2 subagents.

### 9. Copy outputs to the source folder
Write the record and JSON to the source folder too (alongside the original
files), and to the workspace. Then remove staging/scaffolding.

## Known failures / guardrails

- **`00XX` garbled text** — double-encoded font; apply the byte collapse.
- **Empty text layer** — image-only PDF; use the image path.
- **`read_image` not in catalog** — session is on a non-vision model route.
- **Value conflicts between a native PDF and a photo of it** — the photo is a
  re-print; prefer the native-PDF value and flag the difference.
- **Duplicate hashes** — always dedupe before reading.
- **Source documents disagreeing** (DOB, ID, repeated-print values) — OCR cannot
  resolve these; they need a human. Note them, do not fix them.

## Notes

- The helper scripts are **model-free** (stdlib + `Pillow`); they carry no
  patient data. The vision reading and consolidation use the session model.
- Keep outputs and any private values **on disk**; avoid pasting private data
  into the chat beyond what the task needs.
