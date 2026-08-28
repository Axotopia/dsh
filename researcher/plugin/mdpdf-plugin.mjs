// mdpdf-portable — registers the `convert_md_to_pdf` model Tool.
//
// Loaded as an agent-preset row (`name: ./plugin/mdpdf-plugin.mjs`); the
// relative specifier resolves against the preset directory, so this file
// travels with the package. Consumes the HOST services `fs`, `subprocess`,
// and `sandboxPolicy`; publishes no service, so the row needs no realm.
//
// Pipeline: walk *.md/markdown -> built-in Markdown-to-HTML conversion ->
// headless Edge/Chrome --print-to-pdf -> <name>.pdf beside each source.
//
// Deliberately dependency-free: static imports of harness packages do not
// resolve from a preset directory, so the tool definition below is a literal
// ToolDefinition registered through ctx.tools (no @deepseek-ai/dsh-tools
// import). The output schema is canonical JSON Schema in the registry's
// supported subset (type/properties/required/items/additionalProperties).

const SKIP_DIRS = ['node_modules', '.git', '.svn', '.hg', 'dist', 'build', 'out', '.next', '.nuxt',
  'coverage', '.venv', 'venv', '__pycache__', '.idea', '.vscode', '.gradle', '.dsh-md2pdf-tmp']
const FILE_CAP = 25

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function inlinePlain(raw) {
  var t = escapeHtml(raw)
  t = t.replace(/!\[([^\]]*)\]\(\s*([^)\s]+)[^)]*\)/g, function (m, a, b) { return '<img alt="' + a + '" src="' + b + '" />' })
  t = t.replace(/\[([^\]]+)\]\(\s*([^)\s]+)[^)]*\)/g, function (m, a, b) { return '<a href="' + b + '">' + a + '</a>' })
  t = t.replace(/\*\*\*([\s\S]+?)\*\*\*/g, '<strong><em>$1</em></strong>')
  t = t.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/(^|[^\w*])\*(?!\s)([^*\n]+?)\*(?![\w*])/g, '$1<em>$2</em>')
  t = t.replace(/__([\s\S]+?)__/g, '<strong>$1</strong>')
  t = t.replace(/(^|[^\w_])_(?!\s)([^_\n]+?)_(?![\w_])/g, '$1<em>$2</em>')
  t = t.replace(/~~([\s\S]+?)~~/g, '<del>$1</del>')
  return t
}

function inlineMd(src) {
  var out = ''
  var rest = String(src)
  var re = /(`+)([\s\S]*?)\1/
  var m = re.exec(rest)
  while (m !== null) {
    out += inlinePlain(rest.slice(0, m.index))
    out += '<code>' + escapeHtml(m[2].replace(/^ | $/g, '')) + '</code>'
    rest = rest.slice(m.index + m[0].length)
    m = re.exec(rest)
  }
  out += inlinePlain(rest)
  return out
}

var LIST_RE = /^(\s*)([-*+]|\d{1,9}[.)])[ \t]+(.*)$/

function isSepRow(s, headerLine) {
  if (s.indexOf('-') < 0) return false
  var t = s.trim()
  if (!/^[\s|:-]+$/.test(t)) return false
  return t.indexOf('|') >= 0 || (headerLine.split('|').length - 1) >= 2
}

function parseRow(row) {
  var r = row.trim()
  if (r.charAt(0) === '|') r = r.slice(1)
  if (r.charAt(r.length - 1) === '|') r = r.slice(0, -1)
  return r.split('|').map(function (c) { return c.trim() })
}

function parseList(lines, startIdx, itemIndent, depth) {
  var first = LIST_RE.exec(lines[startIdx])
  var ordered = /\d/.test(first[2].charAt(0))
  var items = []
  var cur = null
  var i = startIdx
  while (i < lines.length) {
    var line = lines[i]
    if (/^\s*$/.test(line)) {
      var j = i + 1
      while (j < lines.length && /^\s*$/.test(lines[j])) j++
      if (j >= lines.length) break
      var gap = LIST_RE.exec(lines[j])
      if (gap && gap[1].length >= itemIndent) { i = j; continue }
      break
    }
    var m = LIST_RE.exec(line)
    if (m) {
      var ind = m[1].length
      if (ind < itemIndent) break
      if (ind <= itemIndent + 3) {
        cur = [inlineMd(m[3])]
        items.push(cur)
        i++
        continue
      }
      if (cur === null || depth > 16) break
      var sub = parseList(lines, i, ind, depth + 1)
      cur.push(sub.html)
      i = sub.next
      continue
    }
    if (cur !== null && /^\s+\S/.test(line)) {
      cur.push(inlineMd(line.trim()))
      i++
      continue
    }
    break
  }
  var tag = ordered ? 'ol' : 'ul'
  var html = '<' + tag + '>'
  for (var k = 0; k < items.length; k++) html += '<li>' + items[k].join('') + '</li>'
  html += '</' + tag + '>'
  return { html: html, next: i }
}

function parseBlocks(lines, depth) {
  var out = []
  var i = 0
  if (depth > 20) return escapeHtml(lines.join('\n'))
  while (i < lines.length) {
    var line = lines[i]
    if (/^\s*$/.test(line)) { i++; continue }
    var fence = line.match(/^\s*(```+|~~~+)\s*(\S*)\s*$/)
    if (fence) {
      var marker = fence[1].charAt(0)
      var closeRe = marker === '`' ? /^\s*```\s*$/ : /^\s*~~~\s*$/
      var buf = []
      i++
      while (i < lines.length && !closeRe.test(lines[i])) { buf.push(lines[i]); i++ }
      if (i < lines.length) i++
      var cls = fence[2] ? ' class="language-' + escapeHtml(fence[2]) + '"' : ''
      out.push('<pre><code' + cls + '>' + escapeHtml(buf.join('\n')) + '</code></pre>')
      continue
    }
    var h = line.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/)
    if (h) {
      var lvl = h[1].length
      out.push('<h' + lvl + '>' + inlineMd(h[2]) + '</h' + lvl + '>')
      i++
      continue
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { out.push('<hr />'); i++; continue }
    if (/^\s*>/.test(line)) {
      var q = []
      while (i < lines.length && /^\s*>/.test(lines[i])) { q.push(lines[i].replace(/^\s*>\s?/, '')); i++ }
      out.push('<blockquote>' + parseBlocks(q, depth + 1) + '</blockquote>')
      continue
    }
    if (line.indexOf('|') >= 0 && i + 1 < lines.length && isSepRow(lines[i + 1], line)) {
      var head = parseRow(line)
      var aligns = parseRow(lines[i + 1]).map(function (c) {
        var l = c.charAt(0) === ':'
        var r = c.charAt(c.length - 1) === ':'
        if (l && r) return 'center'
        if (r) return 'right'
        if (l) return 'left'
        return null
      })
      i += 2
      var tbl = '<table><thead><tr>'
      for (var c0 = 0; c0 < head.length; c0++) {
        tbl += '<th' + (aligns[c0] ? ' style="text-align:' + aligns[c0] + '"' : '') + '>' + inlineMd(head[c0]) + '</th>'
      }
      tbl += '</tr></thead><tbody>'
      while (i < lines.length && /\S/.test(lines[i]) && lines[i].indexOf('|') >= 0) {
        var cells = parseRow(lines[i])
        tbl += '<tr>'
        for (var c1 = 0; c1 < head.length; c1++) {
          tbl += '<td' + (aligns[c1] ? ' style="text-align:' + aligns[c1] + '"' : '') + '>' + inlineMd(cells[c1] || '') + '</td>'
        }
        tbl += '</tr>'
        i++
      }
      tbl += '</tbody></table>'
      out.push(tbl)
      continue
    }
    if (LIST_RE.test(line)) {
      var li = LIST_RE.exec(line)
      var parsed = parseList(lines, i, li[1].length, 1)
      out.push(parsed.html)
      i = parsed.next
      continue
    }
    var para = [line]
    i++
    while (i < lines.length && !/^\s*$/.test(lines[i]) && !/^(#{1,6}\s|\s*>|\s*([-*+]|\d{1,9}[.)])\s|\s*```|\s*~~~)/.test(lines[i])) {
      para.push(lines[i])
      i++
    }
    out.push('<p>' + inlineMd(para.join(' ').trim()) + '</p>')
  }
  return out.join('\n')
}

function mdToHtmlBody(md) {
  var text = String(md).replace(/^\uFEFF/, '')
  var fm = text.match(/^---\r?\n[\s\S]*?\r?\n---\s*(\r?\n|$)/)
  if (fm) text = text.slice(fm[0].length)
  return parseBlocks(text.split(/\r?\n/), 1)
}

var DOC_CSS = '@page { size: A4; margin: 16mm 14mm; }' +
  'body { font-family: "Segoe UI", system-ui, -apple-system, sans-serif; font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; margin: 0; }' +
  'h1,h2,h3,h4,h5,h6 { line-height: 1.25; margin: 1.1em 0 0.45em; page-break-after: avoid; }' +
  'h1 { font-size: 1.9em; border-bottom: 1px solid #ddd; padding-bottom: 0.25em; margin-top: 0; }' +
  'h2 { font-size: 1.45em; } h3 { font-size: 1.2em; } h4 { font-size: 1.05em; }' +
  'p { margin: 0.55em 0; }' +
  'pre { background: #f6f8fa; border: 1px solid #e2e5ea; border-radius: 6px; padding: 0.7em 0.9em; white-space: pre-wrap; word-wrap: break-word; font-size: 0.86em; line-height: 1.45; }' +
  'code { font-family: Consolas, "Cascadia Mono", Menlo, monospace; background: #f2f3f5; padding: 0.08em 0.3em; border-radius: 3px; font-size: 0.92em; }' +
  'pre code { background: none; padding: 0; font-size: 1em; }' +
  'blockquote { border-left: 3px solid #c9ced6; margin: 0.7em 0; padding: 0.15em 0.9em; color: #444; background: #fafbfc; }' +
  'table { border-collapse: collapse; margin: 0.8em 0; width: 100%; }' +
  'th, td { border: 1px solid #d6dae0; padding: 0.35em 0.6em; vertical-align: top; }' +
  'th { background: #f3f5f7; }' +
  'img { max-width: 100%; }' +
  'hr { border: none; border-top: 1px solid #ddd; margin: 1.2em 0; }' +
  'ul, ol { padding-left: 1.6em; margin: 0.5em 0; } li { margin: 0.22em 0; }' +
  'a { color: #0969da; text-decoration: none; }' +
  '.doc-footer { margin-top: 2em; padding-top: 0.6em; border-top: 1px solid #eee; color: #888; font-size: 0.75em; }'

function buildDoc(md, sourceName) {
  var title = ''
  var tm = md.match(/^#\s+(.+)$/m)
  if (tm) title = tm[1].replace(/[*_`]/g, '').trim()
  if (!title) title = sourceName.replace(/\.[^.]+$/, '')
  return '<!DOCTYPE html><html><head><meta charset="utf-8"><title>' + escapeHtml(title) + '</title><style>' + DOC_CSS + '</style></head><body>' +
    mdToHtmlBody(md) +
    '<div class="doc-footer">Converted from ' + escapeHtml(sourceName) + '</div></body></html>'
}

function osJoin(base, rel) {
  return base.replace(/[\\/]+$/, '') + '\\' + rel.split('/').join('\\')
}

function formatBytes(b) {
  if (b < 1024) return b + ' B'
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1048576).toFixed(2) + ' MB'
}

function lastLines(text, n) {
  var parts = String(text).split(/\r?\n/).map(function (s) { return s.trim() }).filter(function (s) { return s !== '' })
  return parts.slice(-n).join(' | ').slice(0, 300)
}

export const name = 'tool-md2pdf'
export const inject = ['tools']

export function apply(ctx) {
  const fsSvc = ctx.get('fs')
  const sub = ctx.get('subprocess')
  if (fsSvc === undefined || sub === undefined) {
    console.error('[mdpdf] fs/subprocess services unavailable; convert_md_to_pdf not registered')
    return
  }

  function findBrowserSignal(signal) {
    const probes = [
      ['msedge', 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'],
      ['msedge', 'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'],
      ['chrome', 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'],
      ['chrome', 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe']
    ]
    let chain = Promise.resolve(null)
    probes.forEach(function (p) {
      chain = chain.then(function (prev) {
        if (prev) return prev
        return fsSvc.resolve(p[1], { signal })
          .then(function (t) { return fsSvc.stat(t, signal) })
          .then(function (st) { return st && st.type === 'file' ? { engine: p[0], exe: p[1] } : null })
          .catch(function () { return null })
      })
    })
    return chain.then(function (viaPath) {
      if (viaPath) return viaPath
      const names = ['msedge', 'chrome', 'chromium']
      let chain2 = Promise.resolve(null)
      names.forEach(function (n) {
        chain2 = chain2.then(function (prev) {
          if (prev) return prev
          return sub.resolveExecutable(n, undefined, signal)
            .then(function (exe) { return { engine: n, exe } })
            .catch(function () { return null })
        })
      })
      return chain2
    })
  }

  function collectMarkdown(dirTarget, depth, acc, state, signal) {
    if (state.truncated || depth > 8) return Promise.resolve()
    return fsSvc.listDir(dirTarget, signal).then(function (entries) {
      let chain = Promise.resolve()
      entries.forEach(function (e) {
        chain = chain.then(function () {
          if (state.truncated) return
          if (acc.length >= FILE_CAP) { state.truncated = true; return }
          if (e.type === 'directory') {
            if (SKIP_DIRS.indexOf(e.name.toLowerCase()) >= 0) return
            if (e.name.charAt(0) === '.') return
            return collectMarkdown(e.target, depth + 1, acc, state, signal)
          }
          if (e.type === 'file' && /\.(md|markdown)$/i.test(e.name)) acc.push(e.target)
        })
      })
      return chain
    })
  }

  function resultEntrySchema() {
    return {
      type: 'object',
      additionalProperties: false,
      properties: {
        source: { type: 'string' },
        pdf: { type: 'string' },
        bytes: { type: 'integer' },
        reason: { type: 'string' },
        error: { type: 'string' }
      },
      required: ['source', 'pdf']
    }
  }

  const entrySchema = resultEntrySchema()

  let runCounter = 0

  const tool = {
    name: 'convert_md_to_pdf',
    description: 'Convert Markdown (.md/.markdown) files in the workspace to PDF documents written beside their sources (foo.md -> foo.pdf). Rendering is self-contained (built-in Markdown-to-HTML converter plus headless Edge/Chrome), so no network or LaTeX is needed. Pass path to convert ONE file or ONE directory; omit path to convert every Markdown file found recursively under the workspace root (skipping dependency/build folders, capped at 25 files per call). Supports headings, fenced code, tables, lists, blockquotes, links/images, bold/italic/strikethrough/inline code. YAML front matter is stripped.',
    parameters: {
      type: 'object',
      properties: {
        path: {
          type: 'string',
          description: 'Optional path to a single .md file or a directory of them, relative to the workspace root (or absolute). Omit to convert the whole workspace recursively.'
        },
        overwrite: {
          type: 'boolean',
          description: 'Regenerate the PDF even if it already exists (default true). Set false to skip files whose PDF already exists.'
        }
      }
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          ok: { type: 'boolean' },
          engine: { type: 'string' },
          count: { type: 'integer' },
          converted: { type: 'array', items: entrySchema },
          failed: { type: 'array', items: entrySchema },
          skipped: { type: 'array', items: entrySchema },
          truncated: { type: 'boolean' }
        },
        required: ['ok', 'engine', 'count', 'converted', 'failed', 'skipped', 'truncated']
      },
      render(args, value) {
        const lines = []
        if (value.count === 0 && value.failed.length === 0) {
          lines.push('No Markdown files were found to convert.')
        } else {
          lines.push('Converted ' + value.count + ' Markdown file(s) to PDF' + (value.engine !== 'none' ? ' using ' + value.engine : '') + '.')
        }
        value.converted.forEach(function (c) {
          lines.push('- ' + c.source + ' -> ' + c.pdf + (typeof c.bytes === 'number' ? ' (' + formatBytes(c.bytes) + ')' : ''))
        })
        value.skipped.forEach(function (s) { lines.push('- SKIPPED ' + s.source + ': ' + s.reason) })
        value.failed.forEach(function (f) { lines.push('- FAILED ' + f.source + ': ' + f.error) })
        if (value.truncated) lines.push('(More than ' + FILE_CAP + ' files matched; only the first ' + FILE_CAP + ' were converted. Call again with a narrower path.)')
        return [{ type: 'text', text: lines.join('\n') }]
      }
    },
    timeoutMs: 600000,
    execute(args, exec) {
      const policy = ctx.get('sandboxPolicy')
      const root = policy && typeof policy.workspaceRoot === 'string' ? policy.workspaceRoot : undefined
      if (!root) return Promise.reject(new Error('Workspace root is unavailable (sandboxPolicy service missing); pass an absolute path instead.'))
      const requested = args && typeof args.path === 'string' && args.path.trim() !== '' ? args.path.trim() : '.'
      const overwrite = !(args && args.overwrite === false)
      const signal = exec.signal
      return fsSvc.resolve(requested, { cwd: root, signal }).then(function (rootTarget) {
        return fsSvc.stat(rootTarget, signal).then(function (info) {
          if (!info) throw new Error('Path not found: ' + requested)
          const targets = []
          const state = { truncated: false }
          let prep
          if (info.type === 'directory') {
            prep = collectMarkdown(rootTarget, 0, targets, state, signal)
          } else if (info.type === 'file' && /\.(md|markdown)$/i.test(requested)) {
            targets.push(rootTarget)
            prep = Promise.resolve()
          } else {
            throw new Error('Not a Markdown file (expected .md or .markdown): ' + requested)
          }
          return prep.then(function () {
            if (targets.length === 0) {
              return { ok: true, engine: 'none', count: 0, converted: [], failed: [], skipped: [], truncated: state.truncated }
            }
            return findBrowserSignal(signal).then(function (browser) {
              if (!browser) {
                throw new Error('No Chromium-based browser found for PDF rendering. Install Microsoft Edge or Google Chrome (standard install location), or put msedge/chrome on PATH.')
              }
              runCounter++
              const runStamp = Date.now().toString(36) + '-' + runCounter + '-' + Math.floor(Math.random() * 1e6).toString(36)
              const tmpRoot = osJoin(root, '.dsh-md2pdf-tmp/run-' + runStamp)
              const converted = []
              const failed = []
              const skipped = []
              let chain = Promise.resolve()
              targets.forEach(function (t, idx) {
                chain = chain.then(function () {
                  if (signal.aborted) return
                  const srcOs = fsSvc.processPath(t)
                  const extMatch = /\.(md|markdown)$/i.exec(srcOs)
                  const baseOs = extMatch ? srcOs.slice(0, extMatch.index) : srcOs
                  const pdfOs = baseOs + '.pdf'
                  let pdfTarget = null
                  return fsSvc.resolve(pdfOs, { signal }).then(function (pt) {
                    pdfTarget = pt
                    if (!overwrite) {
                      return fsSvc.stat(pdfTarget, signal).then(function (st) {
                        if (st) {
                          skipped.push({ source: t.displayPath, reason: 'PDF already exists (overwrite=false)' })
                          return null
                        }
                        return 'go'
                      })
                    }
                    return 'go'
                  }).then(function (verdict) {
                    if (verdict === null) return undefined
                    return fsSvc.readText(t, signal).then(function (md) {
                      const htmlDoc = buildDoc(md, t.displayPath)
                      return fsSvc.resolve(tmpRoot + '\\doc-' + idx + '.html', { signal }).then(function (htmlTarget) {
                        return fsSvc.writeText(htmlTarget, htmlDoc, undefined, signal).then(function () {
                          const profOs = tmpRoot + '\\profile-' + idx
                          const argv = [
                            browser.exe,
                            '--headless', '--disable-gpu', '--disable-extensions',
                            '--no-first-run', '--no-default-browser-check', '--mute-audio',
                            '--hide-scrollbars', '--virtual-time-budget=15000',
                            '--no-pdf-header-footer', '--print-to-pdf-no-header',
                            '--user-data-dir=' + profOs,
                            '--print-to-pdf=' + pdfOs,
                            fsSvc.fileUrl(htmlTarget)
                          ]
                          const handle = sub.spawn({
                            argv,
                            cwd: root,
                            stdio: { stdin: 'ignore', stdout: { maxBytes: 32768 }, stderr: { maxBytes: 131072 } },
                            graceMs: 8000,
                            signal
                          })
                          return handle.done.then(function (outcome) {
                            if (outcome.exitCode !== 0) {
                              let errTail = ''
                              try { errTail = handle.collected.stderr.readFrom(0).text } catch (e2) {}
                              throw new Error('renderer exited with code ' + outcome.exitCode + (errTail ? ': ' + lastLines(errTail, 3) : ''))
                            }
                            return fsSvc.stat(pdfTarget, signal).then(function (st2) {
                              if (!st2 || st2.type !== 'file') throw new Error('PDF was not produced at ' + pdfOs)
                              const entry = { source: t.displayPath, pdf: pdfTarget.displayPath }
                              if (typeof st2.size === 'number') entry.bytes = st2.size
                              converted.push(entry)
                            })
                          })
                        })
                      })
                    })
                  }).catch(function (err) {
                    failed.push({ source: t.displayPath, error: String(err && err.message ? err.message : err) })
                  })
                })
              })
              return chain.then(function () {
                return sub.resolveExecutable('pwsh', undefined, signal)
                  .catch(function () {
                    return sub.resolveExecutable('powershell', undefined, signal).catch(function () { return null })
                  })
                  .then(function (psExe) {
                    if (psExe) {
                      try {
                        const cmdText = "Remove-Item -LiteralPath '" + tmpRoot.replace(/'/g, "''") + "' -Recurse -Force -ErrorAction SilentlyContinue"
                        const cleaner = sub.spawn({
                          argv: [psExe, '-NoProfile', '-NonInteractive', '-Command', cmdText],
                          cwd: root,
                          stdio: { stdin: 'ignore', stdout: 'ignore', stderr: 'ignore' },
                          graceMs: 4000,
                          signal
                        })
                        cleaner.done.catch(function () {})
                      } catch (e3) {}
                    }
                    return { ok: true, engine: browser.engine, count: converted.length, converted, failed, skipped, truncated: state.truncated }
                  })
              })
            })
          })
        })
      })
    }
  }

  const disposer = ctx.tools.register(tool)
  ctx.effect(() => disposer)
  console.log('[mdpdf] convert_md_to_pdf registered')
}

export default { name, inject, apply }
