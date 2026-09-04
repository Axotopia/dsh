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
