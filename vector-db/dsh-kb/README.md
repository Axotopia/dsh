# dsh-kb — DSH knowledge base (vector search over your documents)

The code behind DSH's `kb_*` tools (`kb_search`, `kb_ingest`, `kb_status`,
`kb_list`, `kb_forget`, `kb_reingest`, `kb_inspect`): a worker CLI
(`tools/kb.mjs`, plain Node ≥ 23 using the built-in `node:sqlite`) plus a host
plugin (`kb-plugin.mjs`) that registers those tools in every DSH session.

Install (Windows):

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Then pull the embedding model if needed (`ollama pull bge-m3`) and add the
printed `cordis.patch.yml` row. Full documentation and sample prompts live in
the [parent README](../README.md).
