# vector-db

Pick an Ollama `num_ctx` that actually fits your GPU's VRAM, and bake it into a new
model tag — instead of guessing 4096/8192 or hitting an out-of-memory error on a big
long-context prompt.

Two facts drive why this helps:

1. **Ollama defaults `num_ctx` low** (typically 2048–4096). Local models ship with huge
   native contexts (many support 128 K–256 K+), so the default wastes most of the model
   and truncates long code/agent/rag sessions.
2. **The KV cache is what eats VRAM.** The extra memory scales with the context length you
   want. This tool reads a model's real architecture (not a guess) to compute the KV cost
   per token, then picks the largest context that fits your GPU with a safety reserve.

> It is **architecture-aware**: it recognises **dense**, **hybrid attention + SSM**
> (e.g. Qwen3-Next-style, Nemotron-H), **multi-head latent attention (MLA)**
> (DeepSeek/GLM-style), and **sliding-window** (Gemma 3-style) models. For hybrid models
> only the full-attention layers grow with context — that is exactly why those models can
> hold very large contexts cheaply.

---

## What's in this folder

| File | Purpose |
|---|---|
| `optimize_num_ctx.py` | CLI: detect VRAM, analyse models, compute & write Modelfiles, optionally `ollama create` the tags. |
| `ollama_gguf.py` | Dependency-free GGUF metadata reader + architecture inference (weights never loaded). |
| `requirements.txt` | Dependency notes (stdlib-only; lists system prerequisites). |
| `examples/` | Sample Modelfiles showing the output format. |
| `LICENSE` | MIT. |

---

## DSH knowledge base — search your documents (the `kb_*` tools)

This folder also documents the **vector database built into DSH**. It is a separate
feature from the Python CLI above: a plugin mounted in the DSH host that gives **every
session** seven `kb_*` tools backed by a local store — SQLite (via Node's built-in
`node:sqlite`), embeddings from your local Ollama (default model `bge-m3`, 1024-dim),
and **hybrid retrieval** (semantic cosine + SQLite FTS5 keyword, rank-fused). Every
search result carries a citation: source file path, page, and section heading, so
answers stay grounded in your actual documents.

Documents live where they already are (e.g. a network drive) — the store only holds
extracted text, chunks, embeddings, and citation metadata, never the original files.

Where it lives on disk (no need to touch it day-to-day):

| Path | What |
|---|---|
| `%USERPROFILE%\.dsh\kb\tools\kb.mjs` | Worker CLI (parse → chunk → embed → store → search) |
| `%USERPROFILE%\.dsh\kb\data\kb.db` | The SQLite database (the whole store is this one file) |
| profile `cordis.patch.yml` | The `kb-vector-tools` row that mounts the tools into DSH |

**Prerequisites:** Ollama running with an embedding model pulled (default `bge-m3`;
`ollama pull bge-m3`). First-time setup normally happens once, in a DSH session.

### Sample prompts — what's indexed?

> "What's in the knowledge base?"

Runs `kb_status`: collections with active/error/removed document counts, chunk counts,
embedding model per collection, and the most recent per-file errors.

> "List the documents in the codes collection"
>
> "Show me any documents that failed to ingest"

Runs `kb_list` (optionally filtered by collection or `status: active | error | removed`).

### Sample prompts — searching (the main event)

> "Search the codes for dead-end fire apparatus access road requirements"
>
> "What does section D103.4 of the fire code say about turnarounds?"
>
> "How close can a structure be built to a protected wetland?" *(any question the stored
> documents might answer — the agent decides to search and cites what it finds)*
>
> "Search the knowledge base for wire ampacity tables, top 10 results"
>
> "Search only the zoning collection for accessory dwelling unit setbacks"

Notes: exact section numbers hit the keyword channel; paraphrased questions hit the
semantic channel; both are fused automatically. Answers should cite
`source path | page | section` — if an answer lacks a citation, ask for one.

### Sample prompts — adding documents

> "Ingest `Z:\RESOURCE\CODES\IFC\Appendix D_Fire Apparatus Access Roads.pdf` into the codes collection"

One file → extracted, chunked, embedded, stored with citation metadata.

> "Ingest the folder `Z:\RESOURCE\CODES` into the codes collection — start with 25 files"

A folder ingests recursively; every file is indexed all-or-nothing, and failures are
reported per file without stopping the batch. For a first big sync, cap it with a limit
or expect it to run for a while (embedding throughput is typically ~100+ chunks/sec on a
modern GPU).

> "Ingest `D:\notes\_contract_review.md` into a new collection called legal"

Collections are created on first use. Each collection remembers its embedding model —
mixing models inside one collection is refused (drop and rebuild to change models).

Re-ingesting is **idempotent**: unchanged files are skipped by content hash, edited
files are re-chunked and replace their old chunks atomically (old and new versions are
never searchable at the same time).

### Sample prompts — fixing and inspecting

> "Why did some documents fail? Show me the errors"

Failed documents are kept in the store as `status: error` with the reason (corrupt PDF,
unsupported format, no extractable text — e.g. a scanned page needing OCR).

> "Re-ingest `Z:\RESOURCE\CODES\NEC\cc76.pdf` after the fix"

Rebuilds one document from scratch and clears its error state.

> "Show me what got chunked out of that appendix — first 5 chunks"

Runs `kb_inspect`: the document's metadata plus chunk previews with page/heading. Use
this when a document answers poorly and you want to see exactly what the agent sees.

### Sample prompts — removing documents

> "Remove `Z:\RESOURCE\CODES\old-code-2019.pdf` from the knowledge base"

Returns a **preview** of what would be removed — nothing is deleted until you confirm.

> "Yes, apply"
>
> "Actually purge it completely"

Default is a **soft delete** (immediately hidden from search, recoverable);
`purge` hard-deletes the document, its chunks, and index rows. Bulk variants work too:
"remove everything with status error" or "wipe the whole zoning collection" — always
preview-first, and the tool refuses to run without at least one filter.

### Housekeeping tips

- Organize by collection per domain (`codes`, `zoning`, `health`, `finance`, `legal`) —
  searches can be restricted per collection and results always name their collection.
- Obsolete editions: you may keep both old and new editions tagged with different file
  names/collections; the citation tells you which source an answer came from.
- Power users can bypass the chat entirely: `node %USERPROFILE%\.dsh\kb\tools\kb.mjs status`
  (also `ingest`, `search`, `list`, `forget`, `reingest`, `inspect`, `probe`).
- The store is one SQLite file — back it up by copying `kb.db` while DSH is not ingesting.
- Scanned/image-only PDFs currently fail with "no extractable text"; OCR support is a
  planned enhancement (Ollama OCR models can be wired into the worker's parse step).

---

## Install / prerequisites

> **Zero-setup path — let DSH install it for you.** In any DSH session, just
> point it at this repository — no target path, no manual steps:
>
> > "Install the `vector-db` package at
> > https://github.com/Axotopia/dsh/tree/main/vector-db, and verify it
> > runs. **First check the prerequisites — if Python 3.9+ or the Ollama CLI is not
> > installed, install it.** For Python: `winget install Python.Python.3.13` (or the
> > official installer from https://python.org) and add it to PATH. For Ollama:
> > `winget install Ollama.Ollama` (or download from https://ollama.com/download) and make
> > sure the Ollama service is running. Then confirm `python --version` and
> > `ollama --version`. Finally ask it to analyse a local model and show `num_ctx`
> > recommendations (e.g. for `qwen3:8b`). Grant Full Access to the filesystem for this job."
>
> Notes: the package is a **Python CLI**, so the host needs **Python 3.9+** and the
> **Ollama CLI**; the prompt above installs them if they are missing. There is **no
> `pip install`** (the tool uses only the Python standard library) and no build step.
> NVIDIA drivers are needed only for **automatic VRAM detection** (`nvidia-smi`) — that
> one usually ships with your GPU driver rather than being installed by the agent; if it's
> unavailable, pass `--vram-mib` or set `OLLAMA_CTX_VRAM_MIB` instead. Approve any prompts
> the agent raises, and add missing provider/model keys in Settings → Models if a
> referenced model isn't installed. Skip this path if you prefer the deterministic manual
> steps below.

**No `pip install` needed** — the tool is Python 3.9+ standard library only.

You need these installed on the workstation:

| Requirement | Why | How to get |
|---|---|---|
| **Python 3.9+** | Run the tool. | https://python.org (or your OS package manager). Check `python --version`. |
| **Ollama CLI** | Resolve installed model tags and run `ollama create` to bake in `num_ctx`. | https://ollama.com/download |
| **NVIDIA drivers (optional)** | Automatic VRAM detection via `nvidia-smi`. | NVIDIA driver installer (CUDA-capable). |

> If the target machine has **no `nvidia-smi`** (AMD / Apple Silicon / CPU-only), VRAM can
> still be supplied: `--vram-mib` or the `OLLAMA_CTX_VRAM_MIB` environment variable.

### Get the files (manual install)
Clone the repo (or just copy this folder) and step into it:

```bash
git clone https://github.com/Axotopia/dsh.git
cd dsh/vector-db
```

---

## Quick start

### 1. See a recommendation table (no changes made)
```bash
python optimize_num_ctx.py qwen3:8b llama3.1:70b --info-only
```
Omit the model list to auto-discover **every installed local model**:
```bash
python optimize_num_ctx.py --info-only
```
Example output:
```
GPU VRAM: 97887 MiB (~95.6 GiB)
Reserve:  8 GB (overhead 4 + headroom 4) | KV dtype f16

MODEL                                 wt GB   KV/tok kind              native       max  rec ctx    ~VRAM
----------------------------------------------------------------------------------------------------------
qwen3:8b                                4.9     5536  dense              32768      32768    32768     13.2
gpt-oss:20b                             12.1    2294  hybrid            131072    131072   131072     29.8
```
- `KV/tok` — estimated KV-cache bytes consumed per token of context.
- `max` — largest context the GPU could hold (given weights + reserve).
- `rec ctx` — the recommended value (a convenient power-ish size, capped at the model's native
  context). This is the number baked into the generated Modelfile.

### 2. Generate Modelfiles (recommended first)
```bash
python optimize_num_ctx.py qwen3:8b gpt-oss:20b
```
This writes one `Modelfile` per model into `./modelfiles/`, e.g.
```dockerfile
FROM qwen3:8b
# Alternate tag optimised for GPU VRAM (generated by optimize_num_ctx.py)
PARAMETER num_ctx 65536
```
Nothing on your system is changed yet — you can review the files before applying.

### 3. Create the alternate tags
Two equivalent ways:

```bash
# Create a new tag directly from into one Modelfile:
ollama create qwen3:8b-ctx64k -f modelfiles/qwen3-8b-ctx65536

# Or generate AND create all of them in one step:
python optimize_num_ctx.py qwen3:8b gpt-oss:20b --apply
```
The original tags are untouched; you get **new** tags with the context baked in, e.g.
`qwen3:8b-ctx64k`. Use them as normal:
```bash
ollama run qwen3:8b-ctx64k
```

---

## Tuning

| Flag / env | Default | Meaning |
|---|---|---|
| `--vram-mib N` / `OLLAMA_CTX_VRAM_MIB` | auto (nvidia-smi) | Total GPU VRAM in MiB. |
| `--overhead-gb F` | 4 | Compute/activation reserve (GB), e.g. larger for MoE or vision models. |
| `--headroom-gb F` | 4 | Extra safety headroom below the GPU limit (GB). Raise it if a model is tight. |
| `--dtype f16\|f32` | f16 | KV-cache dtype. `f32` doubles the KV cost. |
| `--min-ctx N` | 8192 | Never recommend a context below this. |
| `--outdir DIR` | `./modelfiles` | Where Modelfiles are written. |
| `--info-only` | off | Print the table only; write nothing. |
| `--apply` | off | Also run `ollama create` for every written Modelfile. |
| `--overwrite` | off | Overwrite existing output Modelfiles. |

### Choosing reserves for your hardware
- **Very large GPU (24–96 GB+):** defaults are fine; you can lower `--headroom-gb` to squeeze
  more context.
- **Tight fit (weights already near your VRAM):** the tool caps `max` automatically, but
  raising `--overhead-gb` / `--headroom-gb` lowers the recommended `rec ctx` for safety.
- **Vision models:** a projector + image tokens add a bit of VRAM; bump `--overhead-gb`.

### Re-running after changing your GPU or models
Re-run the same command — it re-detects VRAM and re-analyses the current models. Existing
generated Modelfiles are skipped unless you pass `--overwrite`.

---

## How it works

`ollama_gguf.py` opens a model's GGUF file and reads **only the header + metadata** (never the
weight tensors), so it's fast and safe even for 100 GB models. From the metadata it extracts
the architecture facts that determine KV-cache growth:

- `block_count` (layers), `attention.head_count_kv` (KV heads), `attention.key_length` /
  `value_length` (head dim), and `context_length` (native max).
- It detects **hybrid** models via `full_attention_interval` or a per-layer KV-head array
  (only the full-attention layers grow with context), **MLA** via `attention.kv_lora_rank`
  (compressed latent), and **sliding-window** via `attention.sliding_window`.

`optimize_num_ctx.py` then computes:

```
available_for_kv = VRAM − model_weights − (overhead + headroom)
max_ctx          = min( available_for_kv / KV_bytes_per_token , native_ctx )
recommended      = round_down_to_nice( max_ctx )
```

and writes a `Modelfile` with `FROM <model>` + `PARAMETER num_ctx <recommended>`. Because the
new tag is built from the original model, it inherits the weights, template, projector, and
sampler defaults — only `num_ctx` changes.

---

## Portability & sanitisation notes

- **No hard-coded machine paths.** The tool resolves the Ollama model store from the
  `OLLAMA_MODELS` env var (falls back to `~/.ollama/models`). Nothing references an absolute
  user directory.
- **No model list is bundled.** You pick models on the command line, or the tool discovers
  whatever is installed locally (cloud/virtual models without a local blob are skipped).
- **stdlib-only.** It is easy to vendor into any environment; no build step.
- Adding/removing models or changing VRAM only re-runs the same command.

---

## License

MIT — see `LICENSE`.
