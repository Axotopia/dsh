# ocr-md — verified OCR to Markdown (images & PDFs) for this workstation

An **agent-preset package** for DSH. Sessions started on the *OCR to Markdown*
preset convert images and PDFs into faithful, **cross-verified Markdown** —
plus optional structured JSON — using the **local Ollama model ladder** on this
computer. Two independent model passes + a reconciliation judge, deterministic
provenance manifests, and zero data egress by default.

```
image.jpg ──┐
            ├─► ocr.ps1 ─► <name>.ocr.md   (canonical, cross-verified)
report.pdf ─┘           └► <name>.ocr.manifest.json (models, timings, conflicts)
                        └► <name>.extract.json     (optional, with -Json)
```

## Files

| File | Purpose |
|---|---|
| `agent.cordis.yml` | Composition: OCR persona + standard tool rows |
| `preset.yml` | Display name/description for preset pickers |
| `ocr.ps1` | The pipeline runner (PS 5.1-compatible, no dependencies) |
| `pdf_pages.py` | PDF text-layer check + page rasterization (pypdfium2) |
| `ocr.config.json` | Model ladder, PDF settings, disabled cloud tier |
| `README.md` | This file |

## Install

```
Copy-Item -Recurse ocr-md "$env:USERPROFILE\.dsh\.agent-presets\"
```

Start a session on the **OCR to Markdown** preset. Requirements on this box:
- Ollama running at `127.0.0.1:11434` with the ladder models installed (see config)
- Python launcher `py` + `pypdfium2` for PDFs (`py -m pip install --user pypdfium2`; already installed here)
- Windows PowerShell 5.1 (what `powershell.exe` provides — the script is written for it)

## The model ladder (this machine: RTX PRO 6000 96 GB)

| # | Model | Size | num_ctx | Role |
|---|---|---|---|---|
| 1 | `glm-ocr:bf16` | 2.1 GB (1.1B) | 8192 | pass-1 workhorse (dedicated OCR) |
| 2 | `qwen3.8:27b-bf16-ctx128k` | ~54 GB | 16384 | pass-2 verifier, reconciliation judge, JSON extractor |
| 3 | `ornith-1.5:35b-ctx128k` | 21.1 GB (35B MoE Q4) | 16384 | fallback tier |
| 4 | `qwen3.6:35b-a3b-bf16` | ~70 GB | 16384 | fallback tier |

Rules baked into the pipeline:
- **pass-2 and the judge never use the pass-1 model** (independence), preferring
  `verification.reconcileWith.model` from the config.
- Every tier is tried in order; a crashing tier is skipped automatically, and a
  failing *file* is marked in its manifest and the batch continues.
- `num_ctx` is pinned per model — large MoE models die with
  *CUDA illegal memory access* when Ollama allocates their giant default
  context. If you add a model to the ladder, pin its `num_ctx` too.

## Verification model (how the output is produced)

1. **pass-1** — full verbatim transcription to Markdown (`glm-ocr`).
2. **pass-2** — independent `SECTION | LABEL | VALUE | UNIT | REF RANGE` sweep of every visible cell.
3. **reconcile** — the judge model sees *the image + both passes*, lists every
   disagreement as JSON, and emits the final Markdown; unresolvable disagreements
   stay inline as `[CONFLICT: A=... ; B=...]`.
4. The canonical `.ocr.md` ends with a **Verification report** (models used,
   conflict table). The manifest carries machine-readable conflicts, timings,
   and errors. Raw passes are kept beside the output as provenance.
5. Known failure class this design exists for: `glm-ocr` can *drop a whole
   result column* on dense pages or degenerate into repetition loops (the tail
   is auto-trimmed). Reconciliation + the pass-2 sweep catch exactly that. If
   the judge reports a "large section missing", re-run that file with the roles
   swapped: `-Ladder <verifier>,<pass1model>`.

## Scheduling — phase-batched multi-item runs

A run with **more than one OCR unit** (several images, a multi-page scanned PDF,
or a mixed directory) is scheduled **by phase, not per file**: every item runs
pass-1 first, then every pass-2, then every reconciliation, then assembly, JSON
extraction, and manifests. A single image keeps the exact inline order it always
had.

Why this is faster with zero accuracy cost:

- **Model loads amortize** — each model loads once per run (2 loads) instead of
  up to twice per item (2N). Biggest win when VRAM forces evictions (small GPU,
  long keep-alive gaps) and on multi-page scanned PDFs.
- **Prompt-prefix cache reuse** — within a phase every request shares the
  identical instruction block, so llama.cpp's prefix cache cheapens prefill for
  items 2..N. Per-file alternation clobbers that cache between passes.
- **Requests are stateless** — same model, same image, same prompt, same
  transcription whichever order items run in; `temperature: 0` and pinned
  `num_ctx` are untouched. Only the schedule changed.

Bookkeeping (unchanged guarantees): per-item artifacts keep their names
(`.pass1.md`, `.pass2.txt`, `.reconcile-raw.txt`, `.ocr.md`, manifests);
PDF pages stay under `<name>.pages/`; the batch summary gains `scheduling`
(`phased-batch` | `inline`) and `phases_ms`, and per-file `seconds` now reports
**inference** seconds (wall time is in the console line and `phases_ms`). An
item whose pass-1 fails is skipped in later phases, gets `<name>.ocr.ERROR.txt`
**and** a manifest with `status: "FAILED"`, and the batch continues; a run with
any failed file still exits 1.

## Using OCR from researcher presets (integration)

The `researcher` preset (repo `researcher/` — the installed `researcher-browser`) ships with a
persona line that routes **all** image/PDF text extraction to this pipeline: the agent never
transcribes images itself and never trusts a single vision read — it runs `ocr.ps1`, then reasons
over the `.ocr.md` / `.extract.json` artifacts. Division of labor:

- **ocr-md owns perception** — pixels become verified text of record (two-pass + judge).
- **the researcher agent owns judgment** — triage (what to OCR, which flags), then consolidation,
  anomaly flagging, and cross-page checks on the extracted text.

Requirements on the machine running researcher sessions: this preset installed at
`%USERPROFILE%\.dsh\.agent-presets\ocr-md` (use `INSTALL.cmd` from the repo `ocr-md/` folder),
Ollama reachable with the ladder models pulled (table above), and `py` + `pypdfium2` for PDFs.
Everything stays local; the cloud tier remains off unless all three opt-in conditions (below)
are met. If the pipeline folder is missing, the persona tells the agent to say so and offer the
one-time install instead of improvising extraction.

## Usage

Via the agent persona (recommended): just ask — *"OCR Z:\docs\report.pdf to MD, JSON too"* —
the agent runs the pipeline and consolidates results.

Directly:

```powershell
# single image, verified
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\.agent-presets\ocr-md\ocr.ps1" "Z:\KEE\Health\_Tay\Tay-2025-02-06\Image_20250209201248.jpg" -Json

# whole folder (recursive), MD only
& powershell.exe ... -File "...\ocr-md\ocr.ps1" "Z:\KEE\Health\_Tay\Tay-2025-02-06"

# PDF: text-layer pages used exactly, scanned pages rasterized at 300 dpi + OCR
& powershell.exe ... -File "...\ocr-md\ocr.ps1" "C:\docs\scanned.pdf" -OutDir "C:\docs\out"
```

PDF handling: each page's embedded text layer is quality-gated (≥150 chars with
a digit, or ≥600 chars). Pages passing the gate are used **exactly** (no model);
the rest are rasterized at `pdf.dpi` and run through the OCR ladder. The PDF's
canonical `.ocr.md` is assembled page-by-page with per-page provenance under
`<name>.pages/`.

JSON output (with `-Json`): `{"records":[{"test","value","unit","ref_range","flag","category","date"(,"page" for PDFs)}]}` —
values verbatim, `[CONFLICT:...]` cells carry both readings with `flag:"conflict"`.

## Privacy & the cloud tier

Default: **everything runs locally; documents never leave the machine.**

A cloud tier is configured but **disabled** (`cloud.enabled = false`): DeepSeek
`deepseek-v4-flash-vision-exp` via `https://api.deepseek.com` (OpenAI-compatible,
`Authorization: Bearer $env:DEEPSEEK_API_KEY`). To ever allow it, ALL of:
1. set `cloud.enabled: true` in `ocr.config.json`,
2. set the `DEEPSEEK_API_KEY` environment variable,
3. pass `-CloudOk` for that run (per-run consent — never bake it in).

Documented caveat (from DeepSeek's docs): images are normalized to ~800×800 px
(≤384 image tokens), so dense small-font tables degrade — treat the cloud tier
as an independent second opinion or last-resort fallback, not as the verifier of
record for lab/financial sheets.

## ⚠ Adapting to a lower-spec laptop (e.g. RTX 5090 Laptop 24 GB / 64 GB RAM)

Checklist of the changes needed — do these in `ocr.config.json` (and record any
further tweaks in the log below):

1. **Shrink the ladder** — delete tiers 2–4 (27B/35B models do not fit 24 GB
   once display/WDDM overhead and KV cache are counted). Keep:
   - `glm-ocr:bf16` (2.1 GB) — pass-1, unchanged.
   - add `ornith-1.5:9b` (Q4_K_M ~5.5 GB or Q8_0 ~10 GB; **not** bf16 ~18 GB)
     as the verifier/judge/JSON tier, `num_ctx: 8192`.
2. **Pin `verification.reconcileWith.model`** to that same 9B model (on a
   two-model ladder the judge will be the verifier model — acceptable; the
   pass-2 sweep is still an independent *prompt*, if not an independent *model*).
3. **Lower `pdf.dpi`** to 200 if raster pages OOM the GPU (image tokens grow
   with pixels; 300 dpi A4 PNGs are the worst case).
4. **Expect one-model behavior** — if only `glm-ocr` is installed, the pipeline
   degrades gracefully (pass-2 falls to it too). That weakens verification;
   prefer installing the 9B.
5. **Cloud tier** — this is the box where enabling DeepSeek (see above) makes
   most sense as the *cross-provider* verifier, since local VRAM is tight.
   Keep it opt-in.
6. **Ollama context env** — if a tier still IMA-crashes, also set
   `OLLAMA_CONTEXT_LENGTH=8192` for the Ollama service.
7. Same PowerShell 5.1 + `py` + pypdfium2 requirements as this box.
8. **Phase-batching is your friend here** — with ~12 GB of models on 24 GB,
   per-file alternation between `glm-ocr` and the 9B can evict a model on
   almost every item; the phased scheduler (default for multi-item runs)
   reloads each model only once per run. Don't bypass it with single-file
   invocations in a loop.

VRAM budget sanity for the 9B plan: glm-ocr 2.1 + ornith-9b Q4 5.5 + KV@8k +
image tensors + ~2–3 GB desktop ≈ **11–13 GB** — comfortable headroom on 24 GB.

### Adaptation log (append one line per change, with date + machine)

- 2026-08-31 — created for RTX PRO 6000 96 GB workstation; 4-tier ladder, cloud disabled. (DSH session)
- ____________ — adapted for ____________ ; changes: ____________

## Troubleshooting

- **`Access to the path 'pdf-xxxxxxxx' is denied` in sandboxed sessions**
  (e.g. a DSH session running Workspace Write) — the pipeline used to write its
  scratch dirs only under the preset's own `.work\`, which sits outside the
  session workspace, so the file sandbox denied it and the run needed an
  approval escalation. The work root is now resolved lazily with a writability
  probe: preset `.work\` → hidden `.ocr-work\` beside the output →
  `%TEMP%\ocr-md-work`. Privileged runs keep using `.work\`; sandboxed sessions
  fall back automatically and need no escalation.
- **Run killed at a tool-call wall-clock cap before the judge phase finishes**
  (symptoms: `<doc>.pages\*-pass1.md` and `*-pass2.txt` exist but no canonical
  `.ocr.md`/manifest) — multi-page documents and GPU contention (another OCR
  session sharing Ollama) can exceed a single tool call's budget. The pipeline
  is stateless: relaunch the SAME command in the background (e.g.
  `Start-Process powershell -ArgumentList ... -PassThru`) and poll for
  `.ocr.md` + `.ocr.manifest.json` instead of retrying in the foreground; a
  restart never corrupts anything, it only repeats the model calls.
- **Preset selection silently reverts to the default** (picker shows the
  preset, but new sessions start as "Researcher"/standard) — a composition row
  failed mount validation. Plugin config schemas are strict: `dsh-tool-fs-search`
  **requires** `config.sampleOverCapGlobResults` (this bit us — a config-less
  row is rejected at mount and the GUI keeps the old selection). Validate rows
  against the plugin's exported `Config` schema, or scan with the loader:
  `scanRoot({ path: <preset-root>, trust: 'user' })` from
  `@deepseek-ai/dsh-agent-presets` (shallow check only — it does not resolve
  plugin names or apply configs).
- **"CUDA illegal memory access"** — the model's context allocation; confirm the
  ladder entry pins `num_ctx`, or set `OLLAMA_CONTEXT_LENGTH`. The runner skips
  the dead tier automatically.
- **Empty model responses** — thinking-mode models can spend their whole budget
  on reasoning; keep `temperature: 0` and consider a non-thinking tier.
- **Whole table/column missing from pass-1** — known `glm-ocr` failure mode;
  reconciliation flags it. Re-run with `-Ladder` roles swapped as above.
- **`pdf_pages.py failed (exit 3)`** — `py -m pip install --user pypdfium2`.
- **`Ollama not reachable`** — start Ollama or fix `ollama.baseUrl`.
- Outputs carry a UTF-8 BOM (PowerShell 5.1 `Set-Content -Encoding UTF8`);
  harmless for Markdown readers and JSON parsers used here.

> Trust note: a user-authored preset carries shell-level trust by design — it
> runs local processes and writes files, exactly like the shipped presets do.
> Only distribute this folder through channels you trust.
