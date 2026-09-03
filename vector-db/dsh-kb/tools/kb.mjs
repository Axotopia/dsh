#!/usr/bin/env node
// kb.mjs — DSH knowledge-base worker.
// Parse -> chunk -> embed (Ollama) -> SQLite (node:sqlite), hybrid semantic+keyword search.
// Plain Node.js (>= 23) process: global fetch, process.argv, fs are available here.
// Commands: ingest search status list collections forget reingest inspect probe

import { DatabaseSync } from 'node:sqlite'
import { createHash } from 'node:crypto'
import { promises as fsp, mkdirSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)

// ---------- configuration ----------
const KB_DIR = process.env.KB_DIR || path.join(os.homedir(), '.dsh', 'kb')
const DATA_DIR = path.join(KB_DIR, 'data')
const DB_PATH = path.join(DATA_DIR, 'kb.db')
const OLLAMA_URL = (process.env.KB_OLLAMA_URL || 'http://127.0.0.1:11434').replace(/\/+$/, '')
const DEFAULT_MODEL = 'bge-m3'
const TEXT_EXTS = new Set(['.txt', '.md', '.markdown'])
const PDF_EXTS = new Set(['.pdf'])
const CHUNK_TARGET = 1200
const CHUNK_MAX = 1800
const CHUNK_OVERLAP = 150
const MIN_CHUNK_CHARS = 60
const EMBED_BATCH = 32
const SEARCH_CANDIDATES = 24

// ---------- console helpers ----------
const out = (obj) => process.stdout.write(JSON.stringify(obj, null, 2) + '\n')
const progress = (msg) => process.stderr.write('[kb] ' + msg + '\n')
const fail = (msg, code = 2) => { process.stderr.write('[kb] ERROR: ' + msg + '\n'); process.exit(code) }

// ---------- tiny argv parser ----------
function parseArgs(argv) {
  const opts = { _: [] }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith('--')) {
      const key = a.slice(2)
      const next = argv[i + 1]
      if (next !== undefined && !next.startsWith('--')) { opts[key] = next; i++ }
      else opts[key] = true
    } else opts._.push(a)
  }
  return opts
}

// ---------- database ----------
function openDb() {
  mkdirSync(DATA_DIR, { recursive: true })
  let db
  try { db = new DatabaseSync(DB_PATH) }
  catch (e) { fail('cannot open database ' + DB_PATH + ': ' + e.message, 3) }
  db.exec('PRAGMA journal_mode = WAL;')
  db.exec('PRAGMA busy_timeout = 5000;')
  db.exec('PRAGMA foreign_keys = ON;')
  db.exec(`
    CREATE TABLE IF NOT EXISTS collections(
      name TEXT PRIMARY KEY,
      model TEXT NOT NULL,
      dim INTEGER NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS documents(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      collection TEXT NOT NULL REFERENCES collections(name),
      path TEXT NOT NULL UNIQUE,
      title TEXT,
      content_hash TEXT NOT NULL,
      size INTEGER,
      mtime_ms INTEGER,
      model TEXT NOT NULL,
      dim INTEGER NOT NULL,
      chunk_count INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'active',
      error TEXT,
      ingested_at TEXT,
      updated_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_documents_col_status ON documents(collection, status);
    CREATE TABLE IF NOT EXISTS chunks(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
      ordinal INTEGER NOT NULL,
      page INTEGER,
      heading TEXT,
      text TEXT NOT NULL,
      embedding BLOB NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
    CREATE TABLE IF NOT EXISTS meta(
      key TEXT PRIMARY KEY,
      value TEXT
    );
  `)
  let ftsReady = true
  try { db.prepare('SELECT count(*) AS n FROM chunks_fts').get() }
  catch {
    try { db.exec('CREATE VIRTUAL TABLE chunks_fts USING fts5(text, path UNINDEXED, ordinal UNINDEXED, page UNINDEXED, heading UNINDEXED, doc_id UNINDEXED);') }
    catch (e) { progress('FTS5 unavailable, keyword channel disabled: ' + e.message); ftsReady = false }
  }
  if (ftsReady) {
    const ver = db.prepare("SELECT value FROM meta WHERE key = 'fts_version'").get()
    if (!ver || ver.value !== '2') {
      db.exec('DROP TABLE IF EXISTS chunks_fts;')
      db.exec('CREATE VIRTUAL TABLE chunks_fts USING fts5(text, path UNINDEXED, ordinal UNINDEXED, page UNINDEXED, heading UNINDEXED, doc_id UNINDEXED);')
      const docs = db.prepare('SELECT id, path FROM documents').all()
      const ins = db.prepare('INSERT INTO chunks_fts(text, path, ordinal, page, heading, doc_id) VALUES(?, ?, ?, ?, ?, ?)')
      const getChunks = db.prepare('SELECT ordinal, page, heading, text FROM chunks WHERE doc_id = ? ORDER BY ordinal')
      for (const d of docs) {
        for (const c of getChunks.all(d.id)) ins.run(c.text, d.path, c.ordinal, c.page, c.heading, d.id)
      }
      db.prepare("INSERT OR REPLACE INTO meta(key, value) VALUES('fts_version', '2')").run()
      progress('rebuilt keyword index (fts v2) for ' + docs.length + ' document(s)')
    }
  }
  return db
}

const ftsAvailable = (db) => {
  try { db.prepare('SELECT count(*) AS n FROM chunks_fts').get(); return true }
  catch { return false }
}

// ---------- embeddings ----------
function normalizeVec(arr) {
  const v = Float32Array.from(arr)
  let sum = 0
  for (let i = 0; i < v.length; i++) sum += v[i] * v[i]
  const norm = Math.sqrt(sum)
  if (norm > 0) for (let i = 0; i < v.length; i++) v[i] /= norm
  return v
}

async function embedBatch(model, texts, attempt = 1) {
  try {
    const res = await fetch(OLLAMA_URL + '/api/embed', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model, input: texts, keep_alive: '30m' }),
    })
    if (!res.ok) throw new Error('ollama HTTP ' + res.status + ': ' + (await res.text()).slice(0, 300))
    const data = await res.json()
    if (!Array.isArray(data.embeddings) || data.embeddings.length !== texts.length) {
      throw new Error('ollama returned ' + (data.embeddings ? data.embeddings.length : 'null') + ' embeddings for ' + texts.length + ' inputs')
    }
    return data.embeddings
  } catch (e) {
    if (attempt < 4) {
      await new Promise((r) => setTimeout(r, 600 * attempt))
      return embedBatch(model, texts, attempt + 1)
    }
    throw new Error('embedding failed after ' + attempt + ' attempts: ' + e.message)
  }
}

async function embedTexts(model, texts, label) {
  const vectors = new Array(texts.length)
  for (let i = 0; i < texts.length; i += EMBED_BATCH) {
    const batch = texts.slice(i, i + EMBED_BATCH)
    const embs = await embedBatch(model, batch)
    for (let j = 0; j < embs.length; j++) vectors[i + j] = normalizeVec(embs[j])
    if (texts.length > EMBED_BATCH && label) {
      progress(label + ': embedded ' + Math.min(i + EMBED_BATCH, texts.length) + '/' + texts.length)
    }
  }
  return vectors
}

async function probeDim(model) {
  const [v] = await embedBatch(model, ['dimension probe'])
  return v.length
}

// ---------- extraction ----------
let pdfParseFn
function getPdfParse() {
  if (pdfParseFn !== undefined) return pdfParseFn
  try { pdfParseFn = require('pdf-parse') }
  catch { pdfParseFn = null }
  return pdfParseFn
}

async function extractPdf(filePath) {
  const pdfParse = getPdfParse()
  if (!pdfParse) throw new Error('pdf-parse is not installed (run: npm install --prefix ' + path.join(KB_DIR, 'tools') + ' pdf-parse)')
  const buf = await fsp.readFile(filePath)
  const renderPage = async (pageData) => {
    try {
      const textContent = await pageData.getTextContent({ includeMarkedContent: false })
      let lastY
      const parts = []
      for (const item of textContent.items) {
        if (lastY === item.transform[5] || lastY === undefined) parts.push(item.str)
        else parts.push('\n' + item.str)
        lastY = item.transform[5]
      }
      return parts.join('') + '\f'
    } catch { return '\f' }
  }
  const data = await pdfParse(buf, { pagerender: renderPage })
  return { text: data.text || '', pages: data.numpages || null }
}

// ---------- chunking ----------
const HEADING_RE = /^\s*(?:(#{1,6})\s+(.{2,120})|((?:ARTICLE|SECTION|CHAPTER|APPENDIX|PART|DIVISION|SUBCHAPTER)\b.{0,120})|((?:\d+\.){1,4}\s+\S.{0,120})|(§+\s*[\d.\w-]+.{0,120}))\s*$/i

function chunkExtracted({ text, pages }) {
  // split into pages by form feed (pdf page marker); plain text = one page
  const pageTexts = text.split('\f').map((t) => t.replace(/\r\n?/g, '\n')).filter((t) => t.trim().length > 0)
  const chunks = []
  let curHeading = ''
  let buf = []
  let bufLen = 0

  const flush = (pageNo) => {
    if (bufLen === 0) return
    let body = buf.join('\n').trim()
    if (body.length >= MIN_CHUNK_CHARS || chunks.length === 0) {
      chunks.push({ text: body, page: pageNo, heading: curHeading || null })
    } else if (chunks.length > 0) {
      chunks[chunks.length - 1].text += '\n' + body
    }
    // seed overlap for the next chunk
    if (body.length > CHUNK_OVERLAP) {
      const tail = body.slice(-CHUNK_OVERLAP)
      const cut = tail.indexOf(' ')
      buf = [cut >= 0 ? tail.slice(cut + 1) : tail]
      bufLen = buf[0].length
    } else { buf = []; bufLen = 0 }
  }

  let lastPage = null
  for (let p = 0; p < pageTexts.length; p++) {
    const pageNo = pages ? p + 1 : null
    if (pageNo !== null) lastPage = pageNo
    const lines = pageTexts[p].split('\n')
    for (const rawLine of lines) {
      const line = rawLine.replace(/\s+$/, '')
      const t = line.trim()
      if (t.length === 0) continue
      if (/^(https?:\/\/|www\.)\S+$/i.test(t)) continue
      const m = HEADING_RE.exec(line)
      if (m && t.length > 1) {
        if (bufLen >= 400) flush(pageNo)
        curHeading = t.slice(0, 160)
      }
      if (bufLen + line.length + 1 > CHUNK_MAX) flush(pageNo)
      if (bufLen >= CHUNK_TARGET) flush(pageNo)
      buf.push(line)
      bufLen += line.length + 1
    }
    if (bufLen >= CHUNK_TARGET) flush(pageNo)
  }
  flush(lastPage)
  return chunks
}

// ---------- collection helpers ----------
async function ensureCollection(db, name, model) {
  let row = db.prepare('SELECT name, model, dim FROM collections WHERE name = ?').get(name)
  if (!row) {
    progress('registering collection "' + name + '" with model ' + model + ' (probing dimension via ollama)')
    const dim = await probeDim(model)
    db.prepare('INSERT INTO collections(name, model, dim, created_at) VALUES(?, ?, ?, ?)').run(name, model, dim, new Date().toISOString())
    row = { name, model, dim }
  } else if (model && model !== row.model) {
    fail('collection "' + name + '" uses model "' + row.model + '", not "' + model + '". Drop and rebuild the collection to switch models.', 2)
  }
  return row
}

const sha256File = async (filePath) => createHash('sha256').update(await fsp.readFile(filePath)).digest('hex')

// ---------- ingest ----------
async function ingestFile(db, col, filePath, { force = false } = {}) {
  const st = await fsp.stat(filePath)
  const hash = await sha256File(filePath)
  const existing = db.prepare('SELECT id, content_hash, status FROM documents WHERE path = ?').get(filePath)
  if (!force && existing && existing.content_hash === hash && existing.status === 'active') {
    return { path: filePath, skipped: true, reason: 'unchanged' }
  }

  const ext = path.extname(filePath).toLowerCase()
  let extracted
  if (TEXT_EXTS.has(ext)) {
    extracted = { text: await fsp.readFile(filePath, 'utf8'), pages: null }
  } else if (PDF_EXTS.has(ext)) {
    extracted = await extractPdf(filePath)
  } else {
    throw new Error('unsupported format: ' + ext)
  }

  const chunks = chunkExtracted(extracted)
  if (chunks.length === 0) throw new Error('no extractable text found (scanned image? needs OCR)')

  progress('embedding ' + chunks.length + ' chunks: ' + filePath)
  const vectors = await embedTexts(col.model, chunks.map((c) => c.text), path.basename(filePath))

  const now = new Date().toISOString()
  db.exec('BEGIN IMMEDIATE')
  try {
    if (existing) {
      db.prepare('DELETE FROM chunks WHERE doc_id = ?').run(existing.id)
      if (ftsAvailable(db)) db.prepare('DELETE FROM chunks_fts WHERE doc_id = ?').run(existing.id)
      db.prepare('DELETE FROM documents WHERE id = ?').run(existing.id)
    }
    const info = db.prepare(`
      INSERT INTO documents(collection, path, title, content_hash, size, mtime_ms, model, dim, chunk_count, status, error, ingested_at, updated_at)
      VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', NULL, ?, ?)
    `).run(col.name, filePath, path.basename(filePath, ext), hash, st.size, Math.round(st.mtimeMs), col.model, col.dim, chunks.length, now, now)
    const docId = Number(info.lastInsertRowid)
    const insChunk = db.prepare('INSERT INTO chunks(doc_id, ordinal, page, heading, text, embedding) VALUES(?, ?, ?, ?, ?, ?)')
    const insFts = ftsAvailable(db) ? db.prepare('INSERT INTO chunks_fts(text, path, ordinal, page, heading, doc_id) VALUES(?, ?, ?, ?, ?, ?)') : null
    for (let i = 0; i < chunks.length; i++) {
      const blob = Buffer.from(vectors[i].buffer, vectors[i].byteOffset, vectors[i].byteLength)
      insChunk.run(docId, i, chunks[i].page, chunks[i].heading, chunks[i].text, blob)
      if (insFts) insFts.run(chunks[i].text, filePath, i, chunks[i].page, chunks[i].heading, docId)
    }
    db.exec('COMMIT')
    return { path: filePath, ingested: true, chunks: chunks.length }
  } catch (e) {
    db.exec('ROLLBACK')
    throw e
  }
}

async function cmdIngest(opts) {
  const collection = opts.collection || fail('--collection is required', 2)
  const target = opts.path || opts._[0] || fail('--path (file or folder) is required', 2)
  const model = String(opts.model || DEFAULT_MODEL)
  const force = Boolean(opts.force || opts.reindex)
  const limit = opts.limit ? parseInt(opts.limit, 10) : Infinity

  const db = openDb()
  const col = await ensureCollection(db, collection, model)
  const st = await fsp.stat(target)
  const files = []
  if (st.isDirectory()) {
    await walk(target, files)
  } else {
    files.push(target)
  }
  const supported = files.filter((f) => {
    const ext = path.extname(f).toLowerCase()
    return TEXT_EXTS.has(ext) || PDF_EXTS.has(ext)
  }).slice(0, limit === Infinity ? Infinity : limit)

  if (supported.length === 0) {
    out({ collection, target, scanned: files.length, ingested: 0, skipped: 0, failed: [], note: 'no supported files (.pdf, .txt, .md) found' })
    return
  }

  progress('ingesting ' + supported.length + ' file(s) into "' + collection + '" (model ' + col.model + ')')
  const results = { collection, target, scanned: files.length, supported: supported.length, ingested: 0, skipped: 0, failed: [] }
  for (const f of supported) {
    try {
      const r = await ingestFile(db, col, f, { force })
      if (r.skipped) results.skipped++
      else results.ingested++
    } catch (e) {
      results.failed.push({ path: f, error: e.message })
      recordError(db, collection, f, e.message)
      progress('FAILED ' + f + ': ' + e.message)
    }
  }
  out(results)
  if (results.failed.length > 0) process.exitCode = 1
}

async function walk(dir, acc) {
  let entries
  try { entries = await fsp.readdir(dir, { withFileTypes: true }) }
  catch { return }
  for (const e of entries) {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) await walk(full, acc)
    else if (e.isFile()) acc.push(full)
  }
}

function recordError(db, collection, filePath, message) {
  try {
    const st = fsp.stat // eslint-disable-line
    const existing = db.prepare('SELECT id FROM documents WHERE path = ?').get(filePath)
    const now = new Date().toISOString()
    if (existing) {
      db.prepare("UPDATE documents SET status = 'error', error = ?, updated_at = ? WHERE id = ?").run(message, now, existing.id)
    } else {
      db.prepare(`
        INSERT INTO documents(collection, path, title, content_hash, model, dim, status, error, updated_at)
        VALUES(?, ?, ?, ?, ?, 0, 'error', ?, ?)
      `).run(collection, filePath, path.basename(filePath), 'n/a', DEFAULT_MODEL, message, now)
    }
  } catch { /* management record is best-effort */ }
}

// ---------- search ----------
function ftsQuery(q) {
  const toks = q.replace(/[^\p{L}\p{N}\s.\-]/gu, ' ').split(/\s+/).filter((t) => t.length > 1).slice(0, 12)
  if (toks.length === 0) return null
  return toks.map((t) => '"' + t + '"').join(' OR ')
}

async function cmdSearch(opts) {
  const query = opts.query || opts._.join(' ') || fail('--query "text" (or positional) is required', 2)
  const collection = opts.collection
  const k = opts.k ? parseInt(opts.k, 10) : 6
  const started = Date.now()

  const db = openDb()
  let cols
  if (collection) {
    const c = db.prepare('SELECT name, model, dim FROM collections WHERE name = ?').get(collection)
    if (!c) fail('unknown collection: ' + collection + ' (ingest something first)', 2)
    cols = [c]
  } else {
    cols = db.prepare('SELECT name, model, dim FROM collections').all()
    if (cols.length === 0) fail('no collections exist yet (run ingest first)', 2)
  }

  const combined = new Map() // chunk id -> result
  const addResult = (channel, rank, row) => {
    const rrf = 1 / (60 + rank)
    const key = row.path + '#' + (row.page ?? 'x') + '#' + (row.ordinal ?? 0)
    const prev = combined.get(key)
    if (prev) {
      prev.score += rrf
      prev.channels.push(channel)
    } else {
      combined.set(key, {
        score: rrf,
        channels: [channel],
        path: row.path,
        collection: row.collection,
        page: row.page ?? null,
        heading: row.heading ?? null,
        text: String(row.text).slice(0, 500),
      })
    }
  }

  // semantic channel
  for (const c of cols) {
    const [qv] = await embedTexts(c.model, [query])
    const rows = db.prepare(`
      SELECT c.id, c.ordinal, c.page, c.heading, c.text, c.embedding, d.path, d.collection
      FROM chunks c JOIN documents d ON d.id = c.doc_id
      WHERE d.collection = ? AND d.status = 'active'
    `).all(c.name)
    const scored = new Array(rows.length)
    for (let i = 0; i < rows.length; i++) {
      const u8 = rows[i].embedding
      const v = new Float32Array(u8.buffer, u8.byteOffset, Math.floor(u8.byteLength / 4))
      let dot = 0
      const n = Math.min(qv.length, v.length)
      for (let j = 0; j < n; j++) dot += qv[j] * v[j]
      scored[i] = { row: rows[i], dot }
    }
    scored.sort((a, b) => b.dot - a.dot)
    for (let rank = 0; rank < Math.min(SEARCH_CANDIDATES, scored.length); rank++) {
      addResult('semantic:' + c.name, rank, scored[rank].row)
    }
  }

  // keyword channel
  if (ftsAvailable(db)) {
    const fq = ftsQuery(query)
    if (fq) {
      try {
        const lexRows = db.prepare(`
          SELECT chunks_fts.text, chunks_fts.ordinal, chunks_fts.page, chunks_fts.heading,
                 documents.path, documents.collection,
                 bm25(chunks_fts) AS rank_score
          FROM chunks_fts JOIN documents ON documents.id = chunks_fts.doc_id
          WHERE chunks_fts MATCH ? AND documents.status = 'active'
          ORDER BY rank_score LIMIT ?
        `).all(fq, SEARCH_CANDIDATES * cols.length)
        for (let rank = 0; rank < lexRows.length; rank++) addResult('keyword', rank, lexRows[rank])
      } catch { /* malformed match string; semantic channel still answers */ }
    }
  }

  const results = [...combined.values()].sort((a, b) => b.score - a.score).slice(0, k)
  out({ query, collections: cols.map((c) => c.name), elapsed_ms: Date.now() - started, count: results.length, results })
}

// ---------- management commands ----------
async function cmdStatus() {
  const db = openDb()
  const collections = db.prepare(`
    SELECT c.name, c.model, c.dim, c.created_at,
           SUM(CASE WHEN d.status = 'active' THEN 1 ELSE 0 END) AS active_docs,
           SUM(CASE WHEN d.status = 'error'  THEN 1 ELSE 0 END) AS error_docs,
           SUM(CASE WHEN d.status = 'removed' THEN 1 ELSE 0 END) AS removed_docs,
           COALESCE(SUM(CASE WHEN d.status = 'active' THEN d.chunk_count ELSE 0 END), 0) AS active_chunks
    FROM collections c LEFT JOIN documents d ON d.collection = c.name
    GROUP BY c.name ORDER BY c.name
  `).all()
  const recentErrors = db.prepare(`
    SELECT collection, path, error, updated_at FROM documents
    WHERE status = 'error' ORDER BY updated_at DESC LIMIT 10
  `).all()
  out({ database: DB_PATH, collections, recent_errors: recentErrors })
}

async function cmdList(opts) {
  const db = openDb()
  const conds = []
  const params = []
  if (opts.collection) { conds.push('collection = ?'); params.push(opts.collection) }
  if (opts.status) { conds.push('status = ?'); params.push(opts.status) }
  const where = conds.length ? 'WHERE ' + conds.join(' AND ') : ''
  const limit = opts.limit ? parseInt(opts.limit, 10) : 50
  const rows = db.prepare(`
    SELECT collection, path, title, status, chunk_count, error, ingested_at, updated_at
    FROM documents ${where} ORDER BY updated_at DESC LIMIT ?
  `).all(...params, limit)
  const total = db.prepare('SELECT count(*) AS n FROM documents ' + where).get(...params).n
  out({ total_matching: total, showing: rows.length, documents: rows })
}

async function cmdForget(opts) {
  const db = openDb()
  const yes = Boolean(opts.yes)
  const purge = Boolean(opts.purge)
  const conds = []
  const params = []
  if (opts.path) { conds.push('path = ?'); params.push(opts.path) }
  if (opts.collection) { conds.push('collection = ?'); params.push(opts.collection) }
  if (opts.status) { conds.push('status = ?'); params.push(opts.status) }
  if (conds.length === 0) fail('give --path, --collection and/or --status (refusing to touch everything)', 2)
  const where = 'WHERE ' + conds.join(' AND ')
  const rows = db.prepare('SELECT id, path, collection, status, chunk_count FROM documents ' + where).all(...params)
  if (rows.length === 0) { out({ matched: 0, changed: 0 }); return }

  if (!yes) {
    out({ matched: rows.length, preview: true, action: purge ? 'purge (hard delete)' : 'remove (soft delete, hidden from search)', documents: rows.map((r) => ({ path: r.path, collection: r.collection, chunks: r.chunk_count })), note: 're-run with --yes to apply; add --purge to hard-delete' })
    return
  }
  db.exec('BEGIN IMMEDIATE')
  try {
    if (purge) {
      const ids = rows.map((r) => r.id)
      for (const id of ids) {
        if (ftsAvailable(db)) db.prepare('DELETE FROM chunks_fts WHERE doc_id = ?').run(id)
        db.prepare('DELETE FROM chunks WHERE doc_id = ?').run(id)
        db.prepare('DELETE FROM documents WHERE id = ?').run(id)
      }
    } else {
      db.prepare("UPDATE documents SET status = 'removed', updated_at = ? " + where).run(new Date().toISOString(), ...params)
    }
    db.exec('COMMIT')
    out({ matched: rows.length, changed: rows.length, action: purge ? 'purged' : 'removed' })
  } catch (e) {
    db.exec('ROLLBACK')
    throw e
  }
}

async function cmdReingest(opts) {
  const target = opts.path || opts._[0] || fail('--path is required', 2)
  const db = openDb()
  const doc = db.prepare('SELECT collection FROM documents WHERE path = ?').get(target)
  const collection = opts.collection || (doc && doc.collection) || fail('unknown path; pass --collection', 2)
  const col = db.prepare('SELECT name, model, dim FROM collections WHERE name = ?').get(collection)
  if (!col) fail('unknown collection: ' + collection, 2)
  const result = await ingestFile(db, col, target, { force: true })
  out(result)
}

async function cmdInspect(opts) {
  const target = opts.path || opts._[0] || fail('--path is required', 2)
  const db = openDb()
  const doc = db.prepare('SELECT * FROM documents WHERE path = ?').get(target)
  if (!doc) fail('not in store: ' + target, 2)
  const chunks = db.prepare('SELECT ordinal, page, heading, substr(text, 1, 300) AS preview FROM chunks WHERE doc_id = ? ORDER BY ordinal LIMIT ?').all(doc.id, opts.limit ? parseInt(opts.limit, 10) : 8)
  const { embedding, ...docClean } = doc
  out({ document: docClean, chunks })
}

async function cmdProbe(opts) {
  const model = String(opts.model || DEFAULT_MODEL)
  const started = Date.now()
  const [v] = await embedBatch(model, ['connectivity probe'])
  out({ ollama: OLLAMA_URL, model, dim: v.length, ms: Date.now() - started })
}

// ---------- main ----------
async function main() {
const [cmd, ...rest] = process.argv.slice(2)
try {
  switch (cmd) {
    case 'ingest': return await cmdIngest(parseArgs(rest))
    case 'search': return await cmdSearch(parseArgs(rest))
    case 'status': return await cmdStatus()
    case 'list': return await cmdList(parseArgs(rest))
    case 'collections': return await cmdStatus()
    case 'forget': return await cmdForget(parseArgs(rest))
    case 'reingest': return await cmdReingest(parseArgs(rest))
    case 'inspect': return await cmdInspect(parseArgs(rest))
    case 'probe': return await cmdProbe(parseArgs(rest))
    default:
      out({ usage: 'node kb.mjs <ingest|search|status|list|forget|reingest|inspect|probe> [options]', examples: [
        'node kb.mjs probe',
        'node kb.mjs ingest --collection codes --path "Z:\\RESOURCE\\CODES" --limit 5',
        'node kb.mjs search "setback near wetland" --collection codes --k 6',
        'node kb.mjs status',
      ] })
  }
} catch (e) {
  fail(e && e.stack ? e.stack : String(e), 3)
}
}

main().catch((e) => fail(e && e.stack ? e.stack : String(e), 3))
