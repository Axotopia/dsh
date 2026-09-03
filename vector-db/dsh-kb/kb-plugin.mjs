// kb-plugin.mjs — DSH host-composition plugin: knowledge-base vector search tools.
// Mounted from the profile cordis.patch.yml via a relative-path insert row; the
// heavy lifting lives in the worker CLI beside this file (tools/kb.mjs):
// SQLite (node:sqlite) + Ollama bge-m3 embeddings + hybrid semantic/keyword search.

import os from 'node:os'
import path from 'node:path'

const DEFAULT_KB_DIR = path.join(os.homedir(), '.dsh', 'kb')

export const name = 'kb-vector-tools'
export const inject = ['tools', 'subprocess', 'timer']

export function apply(ctx, config) {
  const kbDir = (config && config.kbDir) || DEFAULT_KB_DIR
  const KB_SCRIPT = path.join(kbDir, 'tools', 'kb.mjs')
  const KB_CWD = path.join(kbDir, 'tools')
  const subprocess = ctx.subprocess

  async function runKb(argv2, timeoutMs) {
    const exe = await subprocess.resolveExecutable('node')
    const handle = subprocess.spawn({
      argv: [exe, KB_SCRIPT].concat(argv2),
      cwd: KB_CWD,
      stdio: {
        stdin: 'ignore',
        stdout: { maxBytes: 512 * 1024, spill: { maxBytes: 8 * 1024 * 1024 } },
        stderr: { maxBytes: 32 * 1024 },
      },
      graceMs: 5000,
    })
    let timedOut = false
    const cancel = ctx.timeout(() => { timedOut = true; try { handle.terminate() } catch (e) {} }, timeoutMs)
    let outcome
    try { outcome = await handle.done } finally { cancel() }
    const read = (r) => { try { return r ? r.readFrom(0).text : '' } catch (e) { return '' } }
    const stdoutText = read(handle.collected.stdout)
    const stderrText = read(handle.collected.stderr)
    if (timedOut) return { error: 'kb worker timed out after ' + timeoutMs + ' ms; it was terminated', stderrTail: stderrText.slice(-500) }
    let parsed = null
    try { parsed = JSON.parse(stdoutText) } catch (e) {}
    return { exitCode: outcome.exitCode, parsed, stdoutText, stderrTail: stderrText.slice(-800) }
  }

  const j = (v, cap) => JSON.stringify(v, null, 2).slice(0, cap || 4000)
  const objectSchema = (properties, required) => {
    const schema = { type: 'object', properties }
    if (required && required.length > 0) schema.required = required
    return schema
  }
  const textOut = { schema: { type: 'string' }, render(_args, value) { return [{ type: 'text', text: value }] } }

  ctx.tools.register({
    name: 'kb_search',
    description: 'Search the local knowledge base (hybrid semantic + keyword over SQLite/Ollama embeddings). Current collections: "codes" (building/fire/electrical code PDFs under Z:\\RESOURCE\\CODES). Returns top-k chunks with citations: source path, page, section heading, text excerpt. Prefer it for any question the stored reference documents may answer, and cite the returned path/page in your answer.',
    parameters: objectSchema({
      query: { type: 'string', description: 'Natural-language question, topic, or code section number to look for' },
      collection: { type: 'string', description: 'Restrict to one collection, e.g. "codes". Omit to search all collections.' },
      k: { type: 'number', description: 'Maximum number of results (default 6, cap 20)' },
    }, ['query']),
    output: textOut,
    async execute(args) {
      const argv2 = ['search', '--query', String(args.query)]
      if (args.collection) argv2.push('--collection', String(args.collection))
      if (args.k) argv2.push('--k', String(Math.max(1, Math.min(20, Number(args.k) || 6))))
      const r = await runKb(argv2, 120000)
      if (r.error) return 'kb_search error: ' + r.error
      if (!r.parsed) return 'kb_search returned non-JSON (exit ' + r.exitCode + '):\n' + (r.stdoutText || r.stderrTail).slice(0, 1000)
      if (!r.parsed.results || r.parsed.results.length === 0) return 'No matches in the knowledge base for: ' + String(args.query)
      const lines = ['Knowledge base results (' + r.parsed.elapsed_ms + ' ms; collections: ' + (r.parsed.collections || []).join(', ') + '):']
      r.parsed.results.forEach((res, i) => {
        lines.push('', '[' + (i + 1) + '] source: ' + res.path + (res.page ? ' | page ' + res.page : '') + (res.heading ? ' | section: ' + res.heading : '') + ' | channels: ' + (res.channels || []).join('+'))
        lines.push(res.text)
      })
      return lines.join('\n')
    },
  })

  ctx.tools.register({
    name: 'kb_ingest',
    description: 'Ingest a document or folder (.pdf, .txt, .md) into the knowledge base: extract text, chunk, embed via local Ollama, store in SQLite. Idempotent: unchanged files are skipped by content hash. Recurses into folders. Each file is indexed all-or-nothing; failures are recorded per-file and reported. Large folders may take minutes.',
    parameters: objectSchema({
      path: { type: 'string', description: 'Absolute file or folder path, e.g. Z:\\RESOURCE\\CODES' },
      collection: { type: 'string', description: 'Collection name, e.g. "codes". Created on first use.' },
      model: { type: 'string', description: 'Embedding model for a NEW collection (default bge-m3). Ignored for existing collections.' },
      limit: { type: 'number', description: 'Cap the number of files processed this call' },
      force: { type: 'boolean', description: 'Re-extract and re-embed even if the file is unchanged' },
    }, ['path', 'collection']),
    output: textOut,
    async execute(args) {
      const argv2 = ['ingest', '--collection', String(args.collection), '--path', String(args.path)]
      if (args.model) argv2.push('--model', String(args.model))
      if (args.limit) argv2.push('--limit', String(Number(args.limit) || 0))
      if (args.force) argv2.push('--force')
      const r = await runKb(argv2, 9 * 60 * 1000)
      if (r.error) return 'kb_ingest error: ' + r.error
      if (!r.parsed) return 'kb_ingest returned non-JSON (exit ' + r.exitCode + '):\n' + (r.stderrTail || r.stdoutText).slice(0, 1200)
      const lines = ['Ingest into "' + r.parsed.collection + '": ingested ' + r.parsed.ingested + ', skipped(unchanged) ' + r.parsed.skipped + ', failed ' + (r.parsed.failed ? r.parsed.failed.length : 0) + '.']
      if (r.parsed.failed && r.parsed.failed.length) {
        lines.push('Failures (kept in the store as status=error; fix the cause and kb_reingest):')
        for (const f of r.parsed.failed) lines.push('  - ' + f.path + ': ' + f.error)
      }
      return lines.join('\n')
    },
  })

  ctx.tools.register({
    name: 'kb_status',
    description: 'Knowledge base health: collections with document/chunk counts by status, plus the most recent per-file errors. Call when the user asks what is indexed or reports search problems.',
    parameters: objectSchema({}, []),
    output: textOut,
    async execute() {
      const r = await runKb(['status'], 30000)
      if (r.error) return 'kb_status error: ' + r.error
      return r.parsed ? j(r.parsed) : 'kb_status returned non-JSON:\n' + (r.stdoutText || r.stderrTail).slice(0, 1000)
    },
  })

  ctx.tools.register({
    name: 'kb_list',
    description: 'List documents known to the knowledge base with status, chunk counts and timestamps. Filter by collection and/or status (active|error|removed).',
    parameters: objectSchema({
      collection: { type: 'string', description: 'Filter by collection name' },
      status: { type: 'string', description: 'Filter by status: active, error, or removed' },
      limit: { type: 'number', description: 'Max rows (default 50)' },
    }, []),
    output: textOut,
    async execute(args) {
      const argv2 = ['list']
      if (args.collection) argv2.push('--collection', String(args.collection))
      if (args.status) argv2.push('--status', String(args.status))
      if (args.limit) argv2.push('--limit', String(Number(args.limit) || 50))
      const r = await runKb(argv2, 30000)
      if (r.error) return 'kb_list error: ' + r.error
      return r.parsed ? j(r.parsed) : 'kb_list returned non-JSON:\n' + (r.stdoutText || r.stderrTail).slice(0, 1000)
    },
  })

  ctx.tools.register({
    name: 'kb_forget',
    description: 'Remove documents from the knowledge base. WITHOUT yes=true this only PREVIEWS what would be removed - show the preview and get explicit user confirmation first. Default is a soft delete (hidden from search, recoverable); purge=true hard-deletes document, chunks and index rows.',
    parameters: objectSchema({
      path: { type: 'string', description: 'Exact source path of one document' },
      collection: { type: 'string', description: 'Match a whole collection' },
      status: { type: 'string', description: 'Match by status, e.g. error' },
      purge: { type: 'boolean', description: 'Hard-delete instead of soft-delete' },
      yes: { type: 'boolean', description: 'true = actually apply (after user confirmation); omit for a preview' },
    }, []),
    output: textOut,
    async execute(args) {
      if (!args.path && !args.collection && !args.status) return 'Refusing to remove everything: give path, collection and/or status.'
      const argv2 = ['forget']
      if (args.path) argv2.push('--path', String(args.path))
      if (args.collection) argv2.push('--collection', String(args.collection))
      if (args.status) argv2.push('--status', String(args.status))
      if (args.purge) argv2.push('--purge')
      if (args.yes) argv2.push('--yes')
      const r = await runKb(argv2, 60000)
      if (r.error) return 'kb_forget error: ' + r.error
      return r.parsed ? j(r.parsed) : 'kb_forget returned non-JSON:\n' + (r.stdoutText || r.stderrTail).slice(0, 1000)
    },
  })

  ctx.tools.register({
    name: 'kb_reingest',
    description: 'Force re-extraction and re-indexing of one document (after the source file changed, after an OCR/parser fix, or to clear an error state).',
    parameters: objectSchema({
      path: { type: 'string', description: 'Source path of the document to rebuild' },
      collection: { type: 'string', description: 'Only needed if the path is not yet in the store' },
    }, ['path']),
    output: textOut,
    async execute(args) {
      const argv2 = ['reingest', '--path', String(args.path)]
      if (args.collection) argv2.push('--collection', String(args.collection))
      const r = await runKb(argv2, 5 * 60 * 1000)
      if (r.error) return 'kb_reingest error: ' + r.error
      return r.parsed ? j(r.parsed) : 'kb_reingest returned non-JSON:\n' + (r.stdoutText || r.stderrTail).slice(0, 1000)
    },
  })

  ctx.tools.register({
    name: 'kb_inspect',
    description: 'Inspect how one document was indexed: metadata plus chunk previews (first ~300 chars each) with page and heading. Use to debug why a document answers poorly or to show the user what got chunked.',
    parameters: objectSchema({
      path: { type: 'string', description: 'Source path of the document' },
      limit: { type: 'number', description: 'Max chunk previews (default 8)' },
    }, ['path']),
    output: textOut,
    async execute(args) {
      const argv2 = ['inspect', '--path', String(args.path)]
      if (args.limit) argv2.push('--limit', String(Number(args.limit) || 8))
      const r = await runKb(argv2, 30000)
      if (r.error) return 'kb_inspect error: ' + r.error
      return r.parsed ? j(r.parsed) : 'kb_inspect returned non-JSON:\n' + (r.stdoutText || r.stderrTail).slice(0, 1000)
    },
  })
}

export default { name, inject, apply }
