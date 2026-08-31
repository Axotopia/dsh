# ocr.ps1 - OCR pipeline runner for the ocr-md preset.
# PowerShell 5.1-compatible. Local-first (Ollama) two-pass verified transcription.
#
#   & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ocr.ps1 <path> [flags]
#
# <path> : one image (.jpg .jpeg .png .webp .gif .bmp) or .pdf, or a directory (recursive)
# Flags : -OutDir <dir>     output directory (default: beside each source file)
#         -Json             also emit <name>.extract.json structured records
#         -SinglePass       skip pass-2/reconciliation (SPEED MODE - not cross-verified)
#         -CloudOk          allow the disabled-by-default cloud tier as LAST-resort fallback
#                           (still needs cloud.enabled=true in config AND the env API key)
#         -Ladder a,b       override ladder order (comma list of model names)
#         -Config <path>    alternate config file
#
# Outputs per file (beside it or in -OutDir):
#   <name>.ocr.md             canonical transcription + verification appendix
#   <name>.pass1.md           raw pass-1 (provenance)
#   <name>.pass2.txt          raw pass-2 (provenance)
#   <name>.reconcile-raw.txt  raw reconciliation output (provenance)
#   <name>.ocr.manifest.json  models, timings, conflicts, errors, provenance
#   <name>.extract.json       only with -Json
#
# Scheduling: a run with MORE THAN ONE work item (several images, or a
# multi-page scanned PDF, or a mixed directory) is PHASE-BATCHED: every item
# runs pass-1 first, then every pass-2, then every reconciliation, then
# assembly / JSON / manifests. Requests are stateless and independent, so
# results are identical to inline processing; the schedule amortizes local
# model loads (2 loads per run instead of up to 2 per item) and lets the
# llama.cpp prompt-prefix cache serve repeated same-phase prefill. A single
# image runs the exact inline order it always has.
#
# Exit code: 0 = all files ok; 1 = one or more files failed (see manifests/batch summary).

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Path,
    [string]$OutDir,
    [switch]$Json,
    [switch]$SinglePass,
    [switch]$CloudOk,
    [string]$Ladder,
    [string]$Config
)

$ErrorActionPreference = 'Stop'
$PresetDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:CfgPath = if ($Config) { (Resolve-Path $Config).Path } else { Join-Path $PresetDir 'ocr.config.json' }
$script:Cfg = Get-Content -Path $script:CfgPath -Raw | ConvertFrom-Json
# Work root is resolved lazily on first use (Get-WorkRoot): prefer the preset's
# own .work, but fall back to a hidden dir beside the output and then %TEMP% so
# sandboxed sessions (e.g. DSH Workspace Write denies writes outside the
# workspace) can run the pipeline without an approval escalation.
$script:WorkRoot = Join-Path $PresetDir '.work'
$script:WorkRootResolved = $false

function Get-WorkRoot([string]$OutDir) {
    if ($script:WorkRootResolved) { return $script:WorkRoot }
    $candidates = @(
        (Join-Path $PresetDir '.work'),
        (Join-Path $OutDir '.ocr-work'),
        (Join-Path ([System.IO.Path]::GetTempPath()) 'ocr-md-work')
    )
    foreach ($c in $candidates) {
        try {
            New-Item -ItemType Directory -Force -Path $c -ErrorAction Stop | Out-Null
            $probe = Join-Path $c ('.probe-' + [guid]::NewGuid().ToString('n').Substring(0, 6) + '.tmp')
            Set-Content -Path $probe -Value 'ok' -ErrorAction Stop
            Remove-Item -Path $probe -Force -ErrorAction SilentlyContinue
            $script:WorkRoot = $c
            $script:WorkRootResolved = $true
            return $script:WorkRoot
        } catch { continue }
    }
    throw ('no writable work root (tried: ' + ($candidates -join '; ') + ')')
}

$script:LadderNames = @()
if ($Ladder) {
    $script:LadderNames = @($Ladder -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
} else {
    $script:LadderNames = @($script:Cfg.ladder | Sort-Object { [int]$_.order } | ForEach-Object { $_.model })
}
$script:ReconcilePreferred = [string]$script:Cfg.verification.reconcileWith.model
$script:B64Cache = @{}

# -- prompts -------------------------------------------------------------------
$script:P_PASS1 = @"
OCR TRANSCRIPTION TASK. You are a precise document OCR engine.
Transcribe this document image COMPLETELY and VERBATIM into clean Markdown.
Preserve: all titles and section headers; person/party names, IDs, MRN/IC numbers, dates and times;
EVERY table with ALL rows, columns, values, units, reference ranges, and flags (such as * or H/L);
notes, remarks, footers, and page indicators (e.g. 'Page 2 of 5').
Rules: use Markdown tables for tables (one header row + separator); keep the document's reading order;
if the same block is printed twice on the page, transcribe it once and add '> note: content duplicated on page'
right after it where it first appears; do NOT add commentary, do NOT paraphrase, do NOT omit lines;
represent empty cells as empty table cells. Output Markdown only, no commentary before/after.
"@

$script:P_PASS2 = @"
FIELD-EXTRACTION TASK (independent verification pass - be exhaustive and literal).
From this document image, list EVERY data cell you can literally see as one line each, in this exact shape:
SECTION | LABEL | VALUE | UNIT | REF RANGE
Cover every table and every labeled field, including header facts (names, IDs, dates, times, page numbers).
Copy values EXACTLY as printed (digits, decimals, %, symbols). If a cell is empty print 'SECTION | LABEL | (blank) | - | -'.
Do not guess values that are not printed. If you cannot read a value clearly, write the label and 'UNREADABLE'.
Plain text lines only, no Markdown formatting, no commentary.
"@

$script:P_RECONCILE = @"
You are a verification judge. The SAME document image is attached. You are given TRANSCRIPTION A (main Markdown)
and TRANSCRIPTION B (extracted field list).
STEP 1 - conflicts: find every disagreement about the same field (different value or text between A and B,
or a field present in one and missing/unreadable in the other). Emit ONE JSON object per line, keys:
{"field":"...","pass1":"...","pass2":"...","note":"..."}
STEP 2 - output format (strict): first print the line @@CONFLICTS@@
then one JSON object per line for each conflict, then the line @@END@@,
then the FINAL RECONCILED Markdown transcription:
- start from TRANSCRIPTION A and fix clear OCR slips using TRANSCRIPTION B or the image;
- where A and B disagree and the image cannot clearly settle it: keep A's value and append [CONFLICT: A=... ; B=...] right after it;
- append a section '## Verification appendix' containing the conflict table and the fields only present in one pass.
Do not omit any value from A. No commentary outside this format.
"@

$script:P_EXJSON = @"
CONVERSION TASK. Convert the document text below into strict JSON for downstream analysis.
Output ONLY a single JSON object (no markdown fences, no commentary), exactly this shape:
{"source":"<SOURCE>","records":[
  {"test":"<label exactly as printed>","value":"<value exactly as printed, keep decimals/symbols>","unit":"<unit or empty>","ref_range":"<reference range or empty>","flag":"<high|low|normal|n/a>","category":"<section/panel name or empty>","date":"<date of the result or empty>"}
]}
Include EVERY result/data field from the text. Keep values verbatim (do not normalize units).
If the text contains a '[CONFLICT: ...]' marker, put BOTH readings in the value as "A=...;B=..." and set flag to "conflict".

DOCUMENT TEXT:
<TEXT>
"@

# -- helpers -------------------------------------------------------------------
function Get-ModelOpts([string]$Model) {
    $entry = $script:Cfg.ladder | Where-Object { $_.model -eq $Model } | Select-Object -First 1
    if ($entry) { return @{ num_ctx = [int]$entry.num_ctx; temperature = [double]$entry.temperature } }
    return @{ num_ctx = 16384; temperature = 0 }
}

function Test-Ollama {
    try { $null = Invoke-RestMethod -Uri $script:Cfg.ollama.baseUrl -TimeoutSec 5; return $true }
    catch { return $false }
}

function Get-B64([string]$File) {
    if ($script:B64Cache.ContainsKey($File)) { return [string]$script:B64Cache[$File] }
    $b = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($File))
    $script:B64Cache[$File] = $b
    return $b
}

function Get-Mime([string]$File) {
    switch -Regex ([System.IO.Path]::GetExtension($File).ToLower()) {
        '\.jpe?g$' { return 'image/jpeg' }
        '\.webp$'  { return 'image/webp' }
        '\.gif$'   { return 'image/gif' }
        '\.bmp$'   { return 'image/bmp' }
        default    { return 'image/png' }
    }
}

function Invoke-Ollama([string]$Model, [string]$Prompt, [string[]]$ImagesB64) {
    $body = @{ model = $Model; prompt = $Prompt; stream = $false; options = (Get-ModelOpts $Model) }
    if ($ImagesB64 -and $ImagesB64.Count -gt 0) { $body.images = @($ImagesB64) }
    $json = $body | ConvertTo-Json -Depth 8
    $t0 = Get-Date
    $r = Invoke-RestMethod -Uri ($script:Cfg.ollama.baseUrl + '/api/generate') -Method Post `
        -Body $json -ContentType 'application/json' -TimeoutSec ([int]$script:Cfg.ollama.generateTimeoutSec)
    $ms = [int]((Get-Date) - $t0).TotalMilliseconds
    Start-Sleep -Milliseconds 250   # be nice to the shared GPU
    return [pscustomobject]@{ text = [string]$r.response; ms = $ms; model = $Model }
}

function Invoke-DeepSeek([string]$Prompt, [string]$File) {
    $keyVar = [string]$script:Cfg.cloud.apiKeyEnv
    $key = [Environment]::GetEnvironmentVariable($keyVar)
    if (-not $key) { throw ("env var " + $keyVar + " not set") }
    $dataUrl = 'data:' + (Get-Mime $File) + ';base64,' + (Get-B64 $File)
    $body = @{
        model       = [string]$script:Cfg.cloud.model
        messages    = @(
            @{ role = 'user'; content = @(
                @{ type = 'text'; text = $Prompt }
                @{ type = 'image_url'; image_url = @{ url = $dataUrl; detail = [string]$script:Cfg.cloud.detail } }
            ) }
        )
        temperature = 0
    } | ConvertTo-Json -Depth 8
    $t0 = Get-Date
    $r = Invoke-RestMethod -Uri ([string]$script:Cfg.cloud.endpoint) -Method Post -Body $body `
        -ContentType 'application/json' -Headers @{ 'Authorization' = ('Bearer ' + $key) } -TimeoutSec 600
    $ms = [int]((Get-Date) - $t0).TotalMilliseconds
    return [pscustomobject]@{ text = [string]$r.choices[0].message.content; ms = $ms; model = ([string]$script:Cfg.cloud.model + ' (cloud)') }
}

# Trim a degenerate repetition tail (e.g. "2 2 2 ..." loops) from model output.
function Trim-Repetition([string]$s) {
    if ([string]::IsNullOrEmpty($s)) { return $s }
    $minRepeat = [int]$script:Cfg.output.trimRepetitionTailMinRepeat
    $maxLen    = [int]$script:Cfg.output.trimRepetitionTailMaxLineLen
    $lines = @($s -split "`n")
    $n = $lines.Count
    if ($n -lt 40) { return $s }
    $start = $n - [int]([Math]::Floor($n * 0.4))
    $counts = @{}
    for ($i = $start; $i -lt $n; $i++) {
        $k = $lines[$i].Trim()
        if ($k.Length -gt 0 -and $k.Length -le $maxLen) {
            if ($counts.ContainsKey($k)) { $counts[$k] = [int]$counts[$k] + 1 } else { $counts[$k] = 1 }
        }
    }
    $repKey = $null
    $max = $minRepeat - 1
    foreach ($k in $counts.Keys) { if ([int]$counts[$k] -gt $max) { $max = [int]$counts[$k]; $repKey = $k } }
    if (-not $repKey) { return $s }
    for ($i = $start; $i -lt $n; $i++) {
        if ($lines[$i].Trim() -eq $repKey) { return (($lines[0..($i - 1)]) -join "`n").TrimEnd() }
    }
    return $s
}

# Try a role against the ladder (skipping $Exclude, preferring $Prefer); last resort: cloud tier.
function Try-Role([string]$Role, [string]$Prompt, [string]$ImageFile, [string[]]$Exclude, [string]$Prefer) {
    $errors = @()
    $order = @()
    if ($Prefer -and $script:LadderNames -contains $Prefer) { $order += $Prefer }
    foreach ($m in $script:LadderNames) { if ($order -notcontains $m) { $order += $m } }

    $b64 = $null
    $hasImage = ($ImageFile -and (Test-Path -LiteralPath $ImageFile))
    if ($hasImage) { $b64 = @(Get-B64 $ImageFile) }

    foreach ($m in $order) {
        if ($Exclude -and $Exclude -contains $m) { continue }
        try { return (Invoke-Ollama $m $Prompt $b64) }
        catch { $errors += ($m + ' : ' + $_.Exception.Message) }
    }
    if (($script:Cfg.cloud.enabled -eq $true) -and $script:CloudOk) {
        try { return (Invoke-DeepSeek $Prompt $ImageFile) }
        catch { $errors += ('cloud : ' + $_.Exception.Message) }
    }
    throw ('all tiers failed for role ' + $Role + ' :: ' + ($errors -join ' || '))
}

function Write-Manifest([System.Collections.IDictionary]$info, [string]$OutDir, [string]$BaseName) {
    $info['config'] = $script:CfgPath
    ($info | ConvertTo-Json -Depth 10) | Set-Content -Path (Join-Path $OutDir ($BaseName + $script:Cfg.output.manifestSuffix)) -Encoding UTF8
}

# -- JSON extraction for one text segment -------------------------------------
function Extract-Json([string]$Source, [string]$TextSegment, [string]$ImageFile, [string[]]$Exclude) {
    $seg = $TextSegment
    if ($seg.Length -gt 60000) { $seg = $seg.Substring(0, 60000) + "`n[...segment truncated for JSON pass...]" }
    $prompt = $script:P_EXJSON.Replace('<SOURCE>', $Source).Replace('<TEXT>', $seg)
    $lastErr = 'n/a'
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        try {
            $r = Try-Role 'exjson' $prompt $ImageFile $Exclude $null
            $clean = (Trim-Repetition $r.text).Trim()
            if ($clean.StartsWith('```')) {
                $clean = [regex]::Replace($clean, '^(?:```[a-zA-Z]*)\s*', '')
                $clean = [regex]::Replace($clean, '\s*```$', '')
            }
            $startI = $clean.IndexOf('{')
            $endI = $clean.LastIndexOf('}')
            if ($startI -lt 0 -or $endI -lt $startI) { throw 'no JSON object found in extraction output' }
            $clean = $clean.Substring($startI, $endI - $startI + 1)
            $obj = $clean | ConvertFrom-Json
            if (-not $obj.records) { throw 'records array missing' }
            $bad = @($obj.records | Where-Object { -not $_.test -or ($null -eq $_.value) })
            if ($bad.Count -gt 0) { throw ([string]$bad.Count + ' records missing test/value') }
            return @{ ok = $true; records = @($obj.records); model = $r.model }
        } catch { $lastErr = $_.Exception.Message }
    }
    return @{ ok = $false; records = @(); error = $lastErr }
}

function Write-ExtractJson($ej, [string]$Path0) {
    if ($ej.ok) {
        $doc = [ordered]@{ records = $ej.records }
        ($doc | ConvertTo-Json -Depth 8) | Set-Content -Path $Path0 -Encoding UTF8
    }
}

# -- work items and phase scheduler --------------------------------------------
# One work item = one OCR unit (a standalone image, or one rasterized PDF page).
# $st is a hashtable holding all per-item state across phases.

function New-WorkItem([string]$ImageFile, [string]$BaseName, [string]$OutDir, [string]$LabelNote) {
    $info = [ordered]@{}
    $info['file']        = $ImageFile
    $info['type']        = 'image'
    $info['created_utc'] = [DateTime]::UtcNow.ToString('o')
    $info['ladder']      = @($script:LadderNames)
    $info['single_pass'] = [bool]$script:SinglePass
    return @{
        src = $ImageFile; base = $BaseName; out = $OutDir; note = $LabelNote
        info = $info
        p1 = $null; t1 = ''; p2 = $null; t2 = ''; rcText = ''
        timings = @{}; errors = @(); conflicts = @()
        failed = $false; failErr = ''; canonical = ''; status = ''
        pdfJob = $null; page = 0
    }
}

function Invoke-Phase([string]$Phase, $st) {
    # pass 1 - transcription (model tier 1 by ladder order)
    if ($Phase -eq 'pass1') {
        if ($st.failed) { return }
        try {
            $p1 = Try-Role 'pass1' $script:P_PASS1 $st.src @() $null
            $st.p1 = $p1
            $st.t1 = (Trim-Repetition $p1.text)
            $st.timings['pass1_ms'] = $p1.ms
            $st.info['pass1_model'] = $p1.model
            ($st.t1) | Set-Content -Path (Join-Path $st.out ($st.base + $script:Cfg.output.passSuffixes.pass1)) -Encoding UTF8
        } catch {
            $st.failed = $true
            $st.failErr = $_.Exception.Message
            $st.errors += ('pass1: ' + $_.Exception.Message)
        }
        return
    }

    # pass 2 - independent field extraction (different model than pass-1)
    if ($Phase -eq 'pass2') {
        if ($st.failed -or $script:SinglePass) { return }
        try {
            $p2 = Try-Role 'pass2' $script:P_PASS2 $st.src @($st.p1.model) $null
            $st.t2 = (Trim-Repetition $p2.text)
            $st.timings['pass2_ms'] = $p2.ms
            $st.info['pass2_model'] = $p2.model
            ($st.t2) | Set-Content -Path (Join-Path $st.out ($st.base + $script:Cfg.output.passSuffixes.pass2)) -Encoding UTF8
        } catch {
            $st.errors += ('pass2: ' + $_.Exception.Message)
            $st.info['pass2_model'] = 'FAILED'
        }
        return
    }

    # reconciliation - a third brain judges A against B and the image
    if ($Phase -eq 'reconcile') {
        if ($st.failed -or $script:SinglePass) { return }
        $judge = $script:P_RECONCILE + "`n`nTRANSCRIPTION A (main Markdown):`n" + $st.t1 + "`n`nTRANSCRIPTION B (field list):`n" + $st.t2
        try {
            $rc = Try-Role 'reconcile' $judge $st.src @($st.p1.model) $script:ReconcilePreferred
            $st.timings['reconcile_ms'] = $rc.ms
            $st.info['reconcile_model'] = $rc.model
            $st.rcText = (Trim-Repetition $rc.text)
            ($st.rcText) | Set-Content -Path (Join-Path $st.out ($st.base + '.reconcile-raw.txt')) -Encoding UTF8
        } catch {
            $st.errors += ('reconcile: ' + $_.Exception.Message)
        }
        return
    }

    # complete - assemble canonical + verification report (pure text work, no model calls)
    if ($Phase -eq 'complete') {
        if ($st.failed) {
            ($st.failErr) | Set-Content -Path (Join-Path $st.out ($st.base + '.ocr.ERROR.txt')) -Encoding UTF8
            $st.status = 'FAILED'
            return
        }
        if ($script:SinglePass) {
            $canonical = $st.t1 + "`n`n---`n`n## Verification report`n`n" +
                "- mode: SINGLE PASS - NOT CROSS-VERIFIED (pass-2/reconciliation skipped by flag)`n" +
                "- pass-1 model: " + $st.p1.model + "`n"
        } elseif ($st.rcText.Length -gt 0) {
            $finalMd = $st.t1
            $i1 = $st.rcText.IndexOf('@@CONFLICTS@@')
            $i2 = if ($i1 -ge 0) { $st.rcText.IndexOf('@@END@@', $i1) } else { -1 }
            if ($i1 -ge 0 -and $i2 -gt $i1) {
                $block = $st.rcText.Substring($i1 + 13, $i2 - $i1 - 13)
                foreach ($ln in ($block -split "`n")) {
                    $t = $ln.Trim()
                    if ($t.StartsWith('{')) {
                        try { $st.conflicts += ,($t | ConvertFrom-Json) }
                        catch { $st.conflicts += ,([pscustomobject]@{ field = $t; note = 'unparseable-conflict-line' }) }
                    }
                }
                $finalMd = $st.rcText.Substring($i2 + 7)
                if ($finalMd.Trim().Length -eq 0) { $finalMd = $st.t1 }
            } else {
                $st.errors += 'reconcile: marker parse failed - canonical is pass-1 text; raw reconciliation kept in provenance file'
            }
            $canonical = $finalMd.Trim() + "`n`n---`n`n## Verification report`n`n" +
                "- mode: two-pass + reconciliation`n" +
                "- pass-1 model: " + $st.p1.model + "`n" +
                "- pass-2 model: " + ([string]$st.info['pass2_model']) + "`n" +
                "- reconcile model: " + ([string]$st.info['reconcile_model']) + "`n" +
                "- conflicts: " + $st.conflicts.Count + "`n"
            if ($st.t2.Length -eq 0) { $canonical += "- pass-2 FAILED (see manifest errors); canonical falls back to pass-1 text`n" }
            if ($st.conflicts.Count -gt 0) {
                $canonical += "`n| field | pass1 | pass2 | note |`n|---|---|---|---|`n"
                foreach ($c in $st.conflicts) {
                    $canonical += '|' + ([string]$c.field).Replace('|','/') + ' | ' + ([string]$c.pass1).Replace('|','/') + ' | ' + ([string]$c.pass2).Replace('|','/') + ' | ' + ([string]$c.note).Replace('|','/') + " |`n"
                }
            }
        } else {
            # reconciliation model call failed entirely
            $canonical = $st.t1 + "`n`n---`n`n## Verification report`n`n" +
                "- mode: two-pass attempt; reconciliation FAILED - canonical is pass-1 text, NOT judged`n" +
                "- pass-1 model: " + $st.p1.model + "`n" +
                "- pass-2 model: " + ([string]$st.info['pass2_model']) + "`n"
        }
        if ($st.note) { $canonical = ([string]$st.note) + "`n`n" + $canonical }
        $st.canonical = $canonical
        ($canonical) | Set-Content -Path (Join-Path $st.out ($st.base + $script:Cfg.output.canonicalSuffix)) -Encoding UTF8
        if ($script:SinglePass) { $st.status = 'ok-single-pass' }
        if ($st.errors.Count -gt 0) { $st.status = 'ok-with-errors' } elseif (-not $st.status) { $st.status = 'ok' }
        $st.info['status'] = $st.status
        $st.info['conflicts'] = @($st.conflicts)
        $st.info['errors'] = @($st.errors)
        $st.info['timings_ms'] = $st.timings
        return
    }

    # json - structured extraction from the finished canonical
    if ($Phase -eq 'json') {
        if ($st.failed -or -not $script:Json) { return }
        $textForJson = if ($script:SinglePass) { $st.t1 } else { $st.canonical }
        $exclude = if ($script:SinglePass) { @() } else { @($st.p1.model) }
        $ej = Extract-Json $st.base $textForJson $st.src $exclude
        $st.info['json_extracted'] = [bool]$ej.ok
        if (-not $ej.ok) { $st.info['json_error'] = [string]$ej.error }
        else { Write-ExtractJson $ej (Join-Path $st.out ($st.base + $script:Cfg.output.jsonSuffix)) }
        return
    }

    # manifest - provenance record (written last so JSON fields are included)
    if ($Phase -eq 'manifest') {
        Write-Manifest $st.info $st.out $st.base
        return
    }
}

# -- PDF pipeline: prepare (rasterize) then complete (assemble) ----------------
function Prepare-Pdf([string]$PdfFile, [string]$BaseName, [string]$OutDir) {
    $pagesDir = Join-Path $OutDir ($BaseName + '.pages')
    New-Item -ItemType Directory -Force -Path $pagesDir | Out-Null
    $work = Join-Path (Get-WorkRoot $OutDir) ('pdf-' + [guid]::NewGuid().ToString('n').Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $work | Out-Null

    $py = Get-Command py -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
    if (-not $py) { throw 'python launcher (py/python) not found - install Python or run: py -m pip install --user pypdfium2' }

    $dpi = [int]$script:Cfg.pdf.dpi
    $minChars = [int]$script:Cfg.pdf.textLayer.minChars
    $pyOut = @()
    & $py.Source (Join-Path $PresetDir 'pdf_pages.py') $PdfFile $work $dpi $minChars 2>&1 | ForEach-Object { $pyOut += [string]$_ }
    if ($LASTEXITCODE -ne 0) { throw ('pdf_pages.py failed (exit ' + $LASTEXITCODE + '): ' + ($pyOut -join ' | ')) }

    $pages = @((Get-Content (Join-Path $work 'pdf_pages.json') -Raw | ConvertFrom-Json))
    $pdfName = [System.IO.Path]::GetFileName($PdfFile)
    $job = @{
        pdfFile = $PdfFile; base = $BaseName; out = $OutDir; pdfName = $pdfName
        pagesDir = $pagesDir; total = $pages.Count
        pageRefs = @(); items = @(); textJson = @()
        pageManifests = @(); allConflicts = @(); failPages = 0
        nText = 0; nRas = 0; scheduling = 'inline'
    }

    foreach ($pg in $pages) {
        $pi = [int]$pg.page
        if ([string]$pg.mode -eq 'textlayer') {
            $job.nText++
            $pfile = Join-Path $work ([string]$pg.file)
            $txt = (Get-Content $pfile -Raw)
            Copy-Item $pfile -Destination (Join-Path $pagesDir ('page-' + ('{0:D3}' -f $pi) + '.txt'))
            $job.pageRefs += ,@{ page = $pi; mode = 'textlayer'; text = $txt }
            if ($script:Json) { $job.textJson += ,@{ page = $pi; base = ($BaseName + '-p' + $pi); text = $txt } }
            continue
        }
        $job.nRas++
        $tag = 'page-' + ('{0:D3}' -f $pi)
        $srcImg = Join-Path $work ($tag + '.png')
        if (-not (Test-Path -LiteralPath $srcImg)) { $srcImg = Join-Path $work ([string]$pg.file) }
        Copy-Item $srcImg -Destination (Join-Path $pagesDir ($tag + '.png'))
        $st = New-WorkItem $srcImg ($BaseName + '-p' + $pi) $pagesDir ("OCR of PDF page - " + $pdfName + ", page " + $pi + " of " + $job.total)
        $st.pdfJob = $job
        $st.page = $pi
        $job.items += ,$st
        $job.pageRefs += ,@{ page = $pi; mode = 'raster'; st = $st }
    }
    return $job
}

function Complete-Pdf($job) {
    $sections = @()
    foreach ($ref in ($job.pageRefs | Sort-Object { $_.page })) {
        if ($ref.mode -eq 'textlayer') {
            $sections += ('## Page ' + $ref.page + ' of ' + $job.total + "  (embedded text layer - exact)`n`n" + $ref.text.Trim() + "`n")
            continue
        }
        $st = $ref.st
        if ($st.failed) {
            $job.failPages++
            $sections += ('## Page ' + $ref.page + ' of ' + $job.total + '  (FAILED: ' + $st.failErr + ')') + "`n"
            $job.pageManifests += ,[ordered]@{ page = $ref.page; mode = 'raster'; status = 'failed'; error = $st.failErr }
            continue
        }
        $sections += ('## Page ' + $ref.page + ' of ' + $job.total + "  (scanned - OCR)`n`n" + $st.canonical.Trim() + "`n")
        $job.pageManifests += ,[ordered]@{
            page = $ref.page; mode = 'raster'; status = [string]$st.status
            pass1_model = [string]$st.info['pass1_model']; pass2_model = [string]$st.info['pass2_model']
            reconcile_model = [string]$st.info['reconcile_model']; json_extracted = $st.info['json_extracted']
            errors = @($st.info['errors'])
        }
        foreach ($c in $st.conflicts) { $job.allConflicts += ,([pscustomobject]@{ page = $ref.page; field = $c.field; pass1 = $c.pass1; pass2 = $c.pass2; note = $c.note }) }
    }

    $header = "# " + [System.IO.Path]::GetFileNameWithoutExtension($job.pdfFile) + "`n`n" +
        "> OCR via the ocr-md preset (local model ladder). Created " + [DateTime]::UtcNow.ToString('o') + "`n" +
        "> Pages: " + $job.total + " (embedded text layer: " + $job.nText + ", rasterized+OCR: " + $job.nRas + "). Raw per-page outputs: " + [System.IO.Path]::GetFileName($job.pagesDir) + "/`n"
    $canonical = $header + "`n" + (($sections -join "`n`n---`n`n").Trim()) + "`n"
    ($canonical) | Set-Content -Path (Join-Path $job.out ($job.base + $script:Cfg.output.canonicalSuffix)) -Encoding UTF8

    $status = 'ok'
    if ($job.failPages -gt 0) { $status = 'ok-with-failed-pages' } elseif ($job.nRas -eq 0) { $status = 'ok-textlayer-exact' }
    $manifest = [ordered]@{}
    $manifest['file'] = $job.pdfFile
    $manifest['type'] = 'pdf'
    $manifest['created_utc'] = [DateTime]::UtcNow.ToString('o')
    $manifest['ladder'] = @($script:LadderNames)
    $manifest['single_pass'] = [bool]$script:SinglePass
    $manifest['scheduling'] = $job.scheduling
    $manifest['pages'] = $job.total
    $manifest['pages_textlayer'] = $job.nText
    $manifest['pages_raster'] = $job.nRas
    $manifest['page_manifests'] = @($job.pageManifests)
    $manifest['conflicts'] = @($job.allConflicts)
    $manifest['status'] = $status
    $manifest['config'] = $script:CfgPath
    ($manifest | ConvertTo-Json -Depth 12) | Set-Content -Path (Join-Path $job.out ($job.base + $script:Cfg.output.manifestSuffix)) -Encoding UTF8

    if ($script:Json) {
        $records = @()
        foreach ($ref in ($job.pageRefs | Sort-Object { $_.page })) {
            $ejf = Join-Path $job.pagesDir ($job.base + '-p' + [int]$ref.page + $script:Cfg.output.jsonSuffix)
            if (-not (Test-Path -LiteralPath $ejf)) { continue }
            try {
                $recs = @(((Get-Content $ejf -Raw | ConvertFrom-Json)).records)
                foreach ($r in $recs) {
                    $r | Add-Member -NotePropertyName page -NotePropertyValue ([int]$ref.page) -Force
                    $records += $r
                }
            } catch { }
        }
        $doc = [ordered]@{ source = $job.pdfName; records = $records }
        ($doc | ConvertTo-Json -Depth 8) | Set-Content -Path (Join-Path $job.out ($job.base + $script:Cfg.output.jsonSuffix)) -Encoding UTF8
    }
    return $status
}

function Get-ItemSeconds($st) {
    $ms = 0
    foreach ($k in $st.timings.Keys) { $ms += [int]$st.timings[$k] }
    return [int]($ms / 1000)
}

# -- main ----------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $Path)) { throw ('path not found: ' + $Path) }
if (-not (Test-Ollama)) { throw ('Ollama not reachable at ' + $script:Cfg.ollama.baseUrl + ' - start it or fix config.ollama.baseUrl') }

$isDir = (Get-Item -LiteralPath $Path).PSIsContainer
if ($isDir) {
    $exts = @('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.pdf')
    $files = @(Get-ChildItem -LiteralPath $Path -Recurse -File |
        Where-Object { -not $_.FullName.Contains('\.') -and $exts -contains $_.Extension.ToLower() -and -not $_.Name.StartsWith('~') } |
        Sort-Object FullName)
} else {
    $files = @(Get-Item -LiteralPath $Path)
}
if ($files.Count -eq 0) { throw ('no supported files found (jpg/jpeg/png/webp/gif/bmp/pdf)') }

# Phase 0 - collect work items (images inline; PDFs rasterized into page items)
$items = @()
$pdfJobs = @()
$prepFail = @{}      # file path -> batch row for files that failed preparation
$firstOutDir = $null

foreach ($f in $files) {
    $name = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
    $oDir = if ($OutDir) { $OutDir } else { $f.DirectoryName }
    if (-not $firstOutDir) { $firstOutDir = $oDir }
    New-Item -ItemType Directory -Force -Path $oDir | Out-Null
    if ($f.Extension.ToLower() -eq '.pdf') {
        Write-Host ("  ... " + $f.FullName + " (preparing pages)") -ForegroundColor Gray
        try {
            $job = Prepare-Pdf $f.FullName $name $oDir
            $pdfJobs += ,$job
            foreach ($st in $job.items) { $items += ,$st }
            Write-Host ("      pages: {0} total ({1} text-layer, {2} raster->OCR)" -f $job.total, $job.nText, $job.nRas) -ForegroundColor Gray
        } catch {
            $errText = $_.Exception.Message
            ($errText) | Set-Content -Path (Join-Path $oDir ($name + '.ocr.ERROR.txt')) -Encoding UTF8
            $prepFail[$f.FullName] = @{ file = $f.FullName; status = 'FAILED'; error = $errText; seconds = 0 }
            Write-Host ("    FAILED: " + $errText) -ForegroundColor Red
        }
    } else {
        Write-Host ("  ... " + $f.FullName) -ForegroundColor Gray
        $items += ,(New-WorkItem $f.FullName $name $oDir $null)
    }
}

$phased = ($items.Count -gt 1)
if ($phased) { foreach ($st in $items) { $st.info['scheduling'] = 'phased-batch' } foreach ($job in $pdfJobs) { $job.scheduling = 'phased-batch' } }
else { foreach ($st in $items) { $st.info['scheduling'] = 'inline' } foreach ($job in $pdfJobs) { $job.scheduling = 'inline' } }

Write-Host ("ocr-md preset :: {0} file(s) :: {1} OCR item(s) :: scheduling = {2} :: ladder = {3} :: singlePass={4} json={5} cloudOk={6}" -f `
    $files.Count, $items.Count, $(if ($phased) { 'phased-batch' } else { 'inline' }), ($script:LadderNames -join ' > '), `
    $script:SinglePass, $script:Json, $script:CloudOk) -ForegroundColor Cyan

# Phases - model calls grouped by role so each local model loads once and the
# prompt-prefix cache serves the identical instruction block across items.
$phaseList = @('pass1')
if (-not $script:SinglePass) { $phaseList += @('pass2', 'reconcile') }
$phaseList += 'complete'
if ($script:Json) { $phaseList += 'json' }
$phaseList += 'manifest'

$phaseMs = [ordered]@{}
foreach ($ph in $phaseList) {
    $swp = [Diagnostics.Stopwatch]::StartNew()
    if ($ph -eq 'pass1')    { Write-Host ("-- phase pass-1 (transcribe) for " + $items.Count + " item(s)") -ForegroundColor Cyan }
    if ($ph -eq 'pass2')    { Write-Host ("-- phase pass-2 (field sweep) for " + $items.Count + " item(s)") -ForegroundColor Cyan }
    if ($ph -eq 'reconcile'){ Write-Host ("-- phase reconcile (judge) for " + $items.Count + " item(s)") -ForegroundColor Cyan }
    if ($ph -eq 'json')     { Write-Host ("-- phase json (structured extract)") -ForegroundColor Cyan }
    foreach ($st in $items) {
        if ($ph -eq 'pass1' -and -not $st.failed) { Write-Host ("   [pass-1] " + $st.base) -ForegroundColor DarkGray }
        Invoke-Phase $ph $st
        if ($ph -eq 'complete' -and $st.status -eq 'FAILED') { Write-Host ("   FAILED: " + $st.base + " :: " + $st.failErr) -ForegroundColor Red }
    }
    if ($ph -eq 'json') {
        foreach ($job in $pdfJobs) {
            foreach ($tj in $job.textJson) {
                $ej = Extract-Json $tj.base $tj.text $null @()
                if ($ej.ok) { Write-ExtractJson $ej (Join-Path $job.pagesDir ($tj.base + $script:Cfg.output.jsonSuffix)) }
            }
        }
    }
    $swp.Stop()
    $phaseMs[$ph] = [int]$swp.Elapsed.TotalMilliseconds
    Write-Host ("   {0}: {1}s" -f $ph, [int]($swp.Elapsed.TotalSeconds)) -ForegroundColor DarkCyan
}

# Assemble PDF-level artifacts and the per-file batch rows
foreach ($job in $pdfJobs) {
    foreach ($st in $job.items) { if (-not $st.failed) { $st.info['status'] = $st.status } }
}

$rows = @()
$failCount = 0
foreach ($f in $files) {
    if ($prepFail.ContainsKey($f.FullName)) { $rows += $prepFail[$f.FullName]; $failCount++; continue }
    $job = $pdfJobs | Where-Object { $_.pdfFile -eq $f.FullName } | Select-Object -First 1
    if ($job) {
        $secs = 0
        foreach ($st in $job.items) { $secs += Get-ItemSeconds $st }
        $stt = Complete-Pdf $job
        $rows += @{ file = $f.FullName; status = $stt; seconds = $secs }
        continue
    }
    $st = $items | Where-Object { $_.src -eq $f.FullName } | Select-Object -First 1
    if ($st) {
        if ($st.status -eq 'FAILED') { $failCount++ }
        $rows += @{ file = $f.FullName; status = $st.status; seconds = (Get-ItemSeconds $st) }
    }
}

if ($rows.Count -gt 1) {
    $summary = [ordered]@{
        created_utc = [DateTime]::UtcNow.ToString('o')
        scheduling = $(if ($phased) { 'phased-batch' } else { 'inline' })
        ladder = @($script:LadderNames)
        singlePass = [bool]$script:SinglePass
        json = [bool]$script:Json
        phases_ms = $phaseMs
        files = @($rows)
    }
    $sName = if ($isDir) { ((Split-Path $Path -Leaf) + '.ocr-batch.json') } else { 'ocr-batch.json' }
    ($summary | ConvertTo-Json -Depth 6) | Set-Content -Path (Join-Path $firstOutDir $sName) -Encoding UTF8
}

$totalSecs = 0
foreach ($r in $rows) { $totalSecs += [int]$r['seconds'] }
Write-Host ("`nocr-md :: complete - {0} ok, {1} failed ({2}s inference total, wall {3}s)" -f ($rows.Count - $failCount), $failCount, $totalSecs, [int](($phaseMs.Values | Measure-Object -Sum).Sum / 1000)) -ForegroundColor Cyan
if ($failCount -gt 0) { exit 1 }
exit 0
