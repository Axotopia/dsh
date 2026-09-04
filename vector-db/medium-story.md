# The First RAG Decision Isn't the Vector Database — It's How Many Tokens Your GPU Can Hold

*We're adding retrieval-augmented generation to DSH, our local-first agent harness. Before arguing about embeddings, we did the math on context windows. This post is written zero-click: the method, the formulas, and the real numbers are all here. If you never click through, you can still do this on your machine tonight.*

**TL;DR**

- On a local-first RAG stack, the binding constraint isn't your embedding model or your vector store. It's how much retrieved context your model can hold in VRAM before it dies with an out-of-memory error.
- Most modern local models aren't plain transformers. Hybrid attention+SSM, multi-head latent attention (MLA), and sliding-window designs change KV-cache cost per token by roughly **60×** between models wearing the same "27B" label.
- So we measured instead of guessed: parse the model's metadata, compute the KV cost per token, bake a safe context length into an alternate model tag, and prove it with a real load test. The whole method is below.

## The reflex, and the constraint nobody argues about

Announce that you're adding RAG and the debate starts immediately: which embedding model, which vector database, HNSW or IVF, chunks of 512 or 1024 tokens. Those are real decisions. They are also not the ones that decide whether your RAG works.

The quiet constraint is the context window. Retrieval is only as good as what you can actually stuff into the model at generation time. Run your stack locally and that window lives in VRAM, next to the model weights — and the default is smaller than you think. Ollama's historical default `num_ctx` has been 2,048–4,096 tokens, while the models themselves ship with native contexts of 128K–256K. Every RAG pipeline built on the default is retrieving documents into a keyhole.

The obvious fix — crank `num_ctx` to the model's maximum — is how you get an out-of-memory crash at the worst possible moment: mid-prompt, with the user watching. We know because we watched it. A sibling pipeline in the same repo pinned this exact failure: large MoE models dying with *CUDA illegal memory access* when Ollama allocated their giant default context, fixed only when context was pinned per model.

That failure is the reason this work exists.

## What we found when we measured instead of guessing

We parsed the GGUF metadata of eight local models — header and key/value section only, never the weight tensors, so it's fast even on 100 GB files — and extracted the facts that actually determine KV-cache growth: layer count, KV heads, head dimension, native context, and the architecture family.

The punchline: **the labels lie, the metadata doesn't.** Per-token KV cost, measured:

- **Hybrid attention + SSM** (Qwen3-Next style, 65 blocks, every 4th layer full attention, 4 KV heads × 256 dim): **≈68 KB/token**
- **Hybrid MoE** (41 blocks, every 4th full attention, 2 × 256): **≈22 KB/token**
- **Nemotron-H style MoE** (88 blocks, only 8 do full attention, 2 × 128): **≈8 KB/token**
- **MLA** (DeepSeek/GLM style, compressed latent shared across heads): tens of KB/token, model-dependent
- **A dense 27B with 62 full-attention layers** (16 KV heads × 128): **≈0.5 MB/token**

Same GPU, same ballpark label, up to a **60-fold difference** in what a token of context costs you. A hybrid MoE holds a quarter-million-token context for the VRAM a dense model spends on 16K. If your RAG planner assumes "bigger model, bigger affordable window," it will be wrong in both directions.

## The math you can steal

```
KV_bytes_per_token ≈ 2 (K and V) × attention_layers × KV_heads × head_dim × bytes_per_element

available_for_kv = VRAM − model_weights − (compute_reserve + safety_headroom)
max_ctx          = min( available_for_kv ÷ KV_bytes_per_token , native_context )
recommended      = round down to a "nice" size: 8k, 16k, 32k, 64k, 128k…
```

Worked example from our 96 GB workstation (RTX PRO 6000 Blackwell, 97,887 MiB):

- Model: a 123B MoE hybrid, Q4 weights ≈ **81 GiB**
- Reserve: 8 GB (4 compute + 4 safety) → about **7 GiB** left for KV
- At 8 KB/token, that's hundreds of thousands of tokens of headroom — capped, sensibly, by the model's own 256K native limit

Then we proved it rather than trusting the arithmetic. Loading that model at 64K context and running real inference: **83,328 MiB used of 97,887, no OOM, ~14 GiB free.** The estimate and the machine agreed. That's the bar: a recommendation you can defend with a screenshot of `nvidia-smi`.

Finally, the result ships as a new tag, not a mutated one: a two-line Modelfile — `FROM <model>` plus `PARAMETER num_ctx <value>` — so the original stays untouched and the new tag inherits the weights, template, and sampler defaults. Your pipelines can then pin context by choosing the tag, which is exactly how the OCR ladder in this repo avoids the illegal-memory-access crashes.

## The decisions — and what actually drives them

Seven principles decided everything above. None of them are about vector databases.

**1. Measure the model, not the label.** "27B" tells you almost nothing about context affordability. Architecture does. Parsing metadata is minutes of work; an OOM in production is an afternoon.

**2. Treat observed failure as a design input.** The CUDA illegal-memory-access crashes weren't hypothetical — they happened on this machine. Any recommendation that could reproduce that failure is dead on arrival.

**3. Non-destructive by default.** Alternate tags, never in-place edits. Reversibility isn't paranoia; it's what lets you experiment at 2 a.m.

**4. A safety margin is a feature.** Compute reserve and headroom are explicit knobs, recommendations round down to memorable sizes, and every number gets validated against a real load before it ships. Conservative where it's cheap (a few GB of VRAM), precise where it matters (the actual limit).

**5. Portability beats cleverness.** The tooling is Python standard library only — no pip, no build step — and resolves the model store from `OLLAMA_MODELS` with a sane fallback. If it needs a week of environment setup, it won't run on the next workstation.

**6. Sanitize for public by construction, not by cleanup.** No absolute paths, no personal model lists baked in. Discovery over hardcoding. A repo you hesitate to push is a repo you'll stop maintaining.

**7. Name things for where they're going.** The folder is called `vector-db`. It contains no vector database yet — it contains the context-budget foundation RAG stands on. Retrieval without a context budget is a demo; with one, it's a system.

## Why the folder is called vector-db

Honesty in naming. RAG in DSH is the destination: local embeddings, local storage, local retrieval, zero data egress. But the first commit isn't a store — it's the budget that decides how much retrieved truth the model can hold. Build the budget first and every later decision (chunk size, top-k, reranking) becomes arithmetic instead of hope. Build the store first and you'll spend a month tuning retrieval into a window the GPU can't open.

## Why we're giving away the whole method

This is the zero-click part, and it's deliberate. Value belongs in the feed, not behind a link. The formulas are above. The measured per-token numbers are above. The failure that motivated it is described above. If this post is all you ever read, you can budget context for your own models tonight with a calculator and `nvidia-smi`.

The repository is the receipt, not the product. If you do click, you get two small Python files that automate exactly what's written here — and a README that answers your question without making you ask twice. Docs should obey the same rule as marketing: complete in place.

## What's next

Embeddings, chunking, and the actual store — chosen last, on purpose, now that the budget is known. The sequence is the strategy: constraint first, components second.

If you run local models, do the math before you pick a database. The math is above; the code is one folder; and your GPU already told you the answer — you just have to read its metadata.

---

# The Store We Chose Last: Planning RAG for Our Agent Harness, One Question at a Time

*This is part two. Part one did the math on context windows — how many retrieved tokens your GPU can actually hold — and ended with a promise: "Embeddings, chunking, and the actual store — chosen last, on purpose." This post is about what happened next, and it starts earlier than you'd expect: the project began as a planning conversation, not a backlog item. As always, this is written zero-click — the formulas, the measured numbers, the schema decisions, the installer, and the exact prompts you'd type are all here. If you never click through, you can build this on your machine tonight.*

**TL;DR**

- The RAG debate everyone has — pgvector vs Qdrant vs Chroma, HNSW vs IVF — dissolved into arithmetic once we wrote down what the corpus actually demands. At personal-corpus scale, **the SQLite engine already built into Node.js is the right answer**: one file, zero installs, zero servers.
- The final stack: **`node:sqlite` + local Ollama embeddings (`bge-m3`, 1,024-dim) + a hybrid retriever** (semantic cosine fused with SQLite FTS5 keyword search). No vector-ship dependencies. No daemon. Backup is `copy kb.db backup.db`.
- Measured on a 96 GB RTX PRO 6000 Blackwell: **~120 chunks embedded per second**, end-to-end search **~100 ms** — including spawning a fresh process, embedding the query on GPU, and scanning the store.
- The feature that makes it a *source of truth* instead of a hint machine: **every result carries a citation — file path, page, section heading.** Retrieval is hybrid because real corpora are bilingual: they speak in exact section numbers *and* in paraphrases.
- The installer is a prompt, and a prompt that silently assumes its environment **fails on machines that aren't yours**. A cross-system test broke ours; the hardening story is below, because it's the part everyone skips.

## The project started as a question, not a backlog

The first session was one sentence of planning, with an explicit instruction: *planning only — no execution, no coding.* The ask, paraphrased: "Is there a way to create a simple vector database for the harness? I have many documents — building codes, zoning codes, health records, financial statements — and I want queries with a source of truth."

That framing decided more than any technology brief could have. Note what's *in* it: **health records** (privacy is a hard requirement before a stack exists), **source of truth** (answers must carry checkable citations), and **simple** (an explicit scope ceiling, which is a gift when you get one).

So before anything was built, the agent did what an agent should do first: **read-only recon of the live system, not the vendor docs.** Three findings shaped everything:

1. The harness's service catalog held roughly sixty services — storage, tools, model routing, sessions — and **not one of them was a vector store.** Nothing to extend; this would be a new capability.
2. The model-routing service was chat-only, and the routed API offers no embeddings endpoint. Embeddings would have to come from a separate local service — which turned out to be already running.
3. The harness's own composition rules answered the architecture question before we asked it: anything shared across sessions belongs to the host composition, not to per-session presets. **One brain, every session reaches into it.**

Planning sessions are where projects quietly die of complexity, so the rule was: every question gets answered by measuring something real. Six questions did the work of an architecture review:

| Question asked | Answer — measured, not guessed | What it decided |
|---|---|---|
| "How complex is SQLite to install on Windows?" | Nothing to install — the runtime (Node 24) ships SQLite built in | Zero database dependencies, ever |
| "Is there a size limit? What about lots of large documents?" | The DB stores *extracted text*, not files. ~470 GB of source ≈ 5–20 GB of text ≈ **20–80 GB of store**, against a 16–288 TB ceiling | The "which vector DB" debate ended before it started |
| "Look at my system" | Ollama already loaded with ~12 embedding models on a 96 GB GPU, running 100% on GPU; a **6.4 TB** network share held the corpus, with a `CODES` folder of ~266 code PDFs | Privacy and throughput were already solved; only wiring remained |
| Which embedding model? | Probed two live: `bge-m3` → 1,024 dims, ~120 chunks/sec batched; `qwen3-embedding:8b` → 4,096 dims, 4× the memory | `bge-m3` default, recorded per collection so collections can differ |
| Where does the database file live? | Local disk, **never the network share** — SMB file locking corrupts live SQLite | One path decision, a corruption class avoided |
| Preset, plugin, or skill? | Shared capability → host-composition plugin; skills only guide behavior | Every future session gets the tools for free |

Two beats from that recon are worth stealing. First, the machine answered questions we hadn't thought to ask: the same probe that measured embedding throughput revealed the GPU was real (100% device utilization, not CPU fallback), and a folder inventory turned "what should we index first?" from a guess into a fact — the codes folder had 266 PDFs sitting in it. Second, the *absence* of assumptions did real work: because nothing was assumed about the corpus, the plan grew a management model before it grew a UI — because the first question after "can it find things?" is always "can I see what it knows, and can I make it forget?"

Then the human said the magic words — "Proceed with the coding" — and the build took hours, not weeks, because every decision had already been paid for.

## The stack, and the math you can steal

**The store is a file.** One `kb.db`, opened by the language runtime itself. The whole database is one ordinary file, so backup is a copy, delete is an uninstall, and the ceiling (roughly 16 TB at default page size, ~288 TB tunable) sits four orders of magnitude above the corpus. Brute-force cosine over 500K vectors at 1,024 dims is about 2 GB of working memory and a few hundred milliseconds — you need millions of chunks before an ANN index earns its complexity.

**The retriever is two channels, rank-fused:**

```
score(chunk) = Σ_channels  1 / (60 + rank_in_channel)
```

Semantic cosine over embeddings answers paraphrases ("how close can I build to a wetland?"); SQLite FTS5 with BM25 answers exact identifiers ("what does D103.4 say?"). Real corpora are bilingual — codes cite themselves in identifiers, humans ask in prose — and a single-channel retriever is a coin flip about which language the question arrives in.

**Chunking is heading-aware:** ~1,200 characters target, 1,800 hard cap, ~150-character overlap, page numbers tracked through PDF page breaks, and a junk filter for the URL-only lines that pollute code-library exports. Each chunk keeps its heading breadcrumb — `Appendix D › SECTION D103 › D103.5` — which is what makes a citation feel like a citation instead of a file name.

**The proof is one query.** Ask *"minimum gate width for fire apparatus access road"* and the answer returns in **99 milliseconds**: `IFC Appendix D, page 2, D103.5 — "The minimum gate width shall be 20 feet (6096 mm)"` — the exact table, on the exact page, checkable against the original PDF. Ask *"D103.4 dead-end requirements"* and the keyword channel lands on Table D103.4 directly. Neither channel alone does both.

**Sizing math, for your own planning:**

```
db_size      ≈ 3–4 × extracted_text        (text ~1×, FTS index ~1–1.5×, embeddings ~1×)
working_RAM  ≈ chunks × dims × 4 bytes      (500K chunks @ 1024-d ≈ 2 GB)
ingest_time  ≈ chunks ÷ measured_chunks_per_second    (1M chunks ≈ 2.3 h on our GPU)
```

## The shape: a worker, a plugin, and a patch row

Three pieces, each boring on purpose:

- **A worker CLI** — one plain JavaScript file doing parse → chunk → embed → store → search, plus management verbs (`status`, `list`, `forget`, `reingest`, `inspect`). It's an ordinary process, so it's testable standalone: `kb.mjs probe` answers "are Ollama, the model, and the database alive?" in one line of JSON.
- **A plugin** that registers seven tools into every session — `kb_search`, `kb_ingest`, `kb_status`, `kb_list`, `kb_forget`, `kb_reingest`, `kb_inspect` — and shells out to the worker. The agent never touches the database; it speaks to a CLI with JSON in and citations out.
- **A patch row** in the harness's composition that mounts the plugin permanently. We prototyped as a session-scoped dynamic plugin first, then promoted — and because the harness live-reloads its composition, the promotion was **verified by subtraction**: stop the prototype, watch the tools survive. The demo is not the deployment until it survives its own uninstall.

Deletion fails closed: preview before it acts, soft-delete by default, purge only on explicit confirmation, and a refusal to run without at least one filter — "remove everything" is a sentence the tool answers with a refusal. Ingestion is idempotent by content hash, and a document is indexed all-or-nothing; an edited file replaces its old chunks atomically, so old and new versions of a code section are never both true at once. Errors are data: a failed document is recorded *in the store* with its reason, listable, fixable with a re-ingest verb. Silent partial failure is how RAG systems start lying.

## The bugs we're proud of

An agent wrote this code, and the real corpus immediately earned its keep. In the first hour against real PDFs: an async function's Promise bound into SQLite as a parameter; FTS rows collapsing into a single result key (sixteen keyword hits stacking onto one chunk); SQLite's `MATCH`-with-table-alias quirk; a top-level `return` that only fails in module scope. None of these appear in a hello-world. All appear in week one of a real corpus. And the corpus handed us a gift: a genuinely corrupt PDF (broken DEFLATE streams) that the pipeline refused to ingest and recorded as `status: error` — the designed behavior, firing for real for the first time. **Testing against your actual documents is not validation theater; it's the debugger.**

## The decisions — and what actually drives them

**1. Plan before you build — but plan by measuring.** The project was born as a planning-only session, and the plan's quality came from recon of a live system, not from opinions. Every early question was answered with a probe, an inventory, or a measured latency.

**2. The store is a file, not a service.** Nothing to run, monitor, or authenticate to. Write the scale requirement down first and the vector-database debate ends before it starts.

**3. Local-first is a privacy architecture, not an aesthetic.** The moment health records appeared in the corpus, "which embedding API is cheapest" stopped being a question. Local embeddings mean sensitive text never crosses a network boundary at all.

**4. Hybrid retrieval, because your corpus is bilingual.** Exact identifiers and paraphrases are both real queries. Fuse two cheap channels instead of betting on one.

**5. Errors are data, not exceptions.** Failed documents live in the store with their reasons. Silent partial failure is how retrieval systems start lying.

**6. Destructive operations fail closed.** Preview, soft-delete, refuse unscoped destruction. This is the same principle as part one's "alternate tags, never in-place edits" — reversibility applied to data instead of models.

**7. The promotion path is part of the design.** Prototype in-session, promote to the composition, verify by subtraction. If demo-to-deployment needs a meeting, you built a demo.

**8. Assume hostile environments — starting with your own.** The installer probes every npm candidate with a real `--version` because *our own PATH shipped a broken npm shim*. If it can break here, it will break on yours.

**9. Documentation is part of the artifact.** The README carries the actual prompts — "what's indexed," "add this folder," "why did this fail," "remove that file" — because a feature whose usage lives in one person's head has one user.

## The installer is a prompt — so we hardened it like code

The part we almost skipped, and the cross-system test caught.

The README offers a zero-setup path: paste one prompt into any DSH session and let the agent install everything. The first version said, in essence, *"install the package at this URL and verify it runs."* On the machine we wrote it on, it worked. On a **different system**, it failed — the prompt silently assumed its environment. Python missing, Ollama missing, and nothing in the instructions told the agent to notice.

The fix wasn't more automation — it was making the environment contract explicit *inside the prompt*: check prerequisites first; if Python 3.9+ or the Ollama CLI is missing, install them (`winget install Python.Python.3.13`, `winget install Ollama.Ollama`); confirm `python --version` and `ollama --version`; *then* install and run. That hardened paragraph now lives in the README:

> *"First check the prerequisites — if Python 3.9+ or the Ollama CLI is not installed, install it… Then confirm `python --version` and `ollama --version`."*

The lesson generalizes: **when your installer is a prompt, the prompt is the installer.** It needs what install scripts need — declared dependencies, verification steps, explicit failure modes — and it must be tested on a machine that isn't yours. "Works on my machine" was always an embarrassment; for prompts it's a new category, because the machine includes whatever the agent finds when it looks around.

## The agent built its own memory

One more thing, and it's why the numbers above can be trusted: **the agent that lives in this harness built the harness's memory.** It measured its host's GPU, enumerated the service catalog, wrote the worker, ingested real codes, hit the corrupt PDF and the SQL quirks, fixed them, promoted itself and verified the promotion by uninstalling itself — and then answered the first question from the store it had just built, correctly, with a page number. Within hours there was a second collection in the store, created by the human, without asking us how. That's the adoption metric that matters: **the tool got used before the documentation was finished.**

Dogfooding at this depth isn't a pose. It's the only way to learn that idempotency, error rows, and citations aren't features — they're the product.

## What's next

OCR for the scanned PDFs (local vision models are already on the machine; the parse step just needs the rung), more collections — health, finance, zoning — and eventually a small GUI panel. Chosen in that order, for the same reason as everything else: each is only worth building now that the layer under it is measured and boring.

The series so far, in one sentence each: *budget first* (part one — how many tokens your GPU holds), *then the store* (part two, this post — one file, one model, two channels, citations everywhere), *then the installer is a prompt and must be hardened like code.* If you run local models, you can have this tonight: the math is above, the stack is one file plus one model, and your documents are already on disk. The only question left is the one you should answer before you write any code at all — and it's the question this whole effort started with, in a planning session where nobody was allowed to write code yet:

*What do your documents actually demand? Write that down first. The stack will introduce itself.*
