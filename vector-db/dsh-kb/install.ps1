<#
.SYNOPSIS
  Install the DSH knowledge base (the kb_* tools): worker + plugin + dependency.

.DESCRIPTION
  Copies kb.mjs (worker CLI) and kb-plugin.mjs into %USERPROFILE%\.dsh\kb,
  installs the single npm dependency (pdf-parse) if Node/npm are available,
  and prints the remaining manual steps (Ollama model + the cordis.patch.yml
  row that mounts the tools into DSH).

  Run from this folder:
    powershell -ExecutionPolicy Bypass -File .\install.ps1
  Custom target:
    .\install.ps1 -KbDir "D:\somewhere\kb" -NoDeps

#>
param(
    [string]$KbDir = (Join-Path $HOME '.dsh\kb'),
    [switch]$NoDeps
)

$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot
$tools = Join-Path $KbDir 'tools'

Write-Host "== DSH knowledge base installer ==" -ForegroundColor Cyan
Write-Host "Target: $KbDir"

# --- 1. Node.js check -------------------------------------------------------
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    $version = (& node --version) -replace '^v', ''
    $major = [int]($version.Split('.')[0])
    if ($major -lt 23) {
        Write-Warning "Node.js v$version found; node:sqlite needs Node >= 23 (24 LTS recommended). Install from https://nodejs.org and re-run."
    } else {
        Write-Host "[ok] Node.js v$version"
    }
} else {
    Write-Warning "Node.js not found on PATH. It is required (Node >= 23, 24 LTS recommended): https://nodejs.org"
}

# --- 2. copy files ----------------------------------------------------------
New-Item -ItemType Directory -Force -Path $tools | Out-Null
Copy-Item (Join-Path $src 'tools\kb.mjs')        (Join-Path $tools 'kb.mjs')        -Force
Copy-Item (Join-Path $src 'tools\package.json')  (Join-Path $tools 'package.json')  -Force
Copy-Item (Join-Path $src 'kb-plugin.mjs')       (Join-Path $KbDir 'kb-plugin.mjs') -Force
Write-Host "[ok] copied worker + plugin"

# --- 3. npm dependency (pdf-parse) ------------------------------------------
if ($NoDeps) {
    Write-Host "[skip] -NoDeps given; run manually:  npm install --prefix `"$tools`" pdf-parse"
} else {
    # Probe candidate npm launchers and keep the first that actually works
    # (PATH shims wrapping a Node runtime without npm are common).
    $candidates = @()
    $cmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
    $candidates += (Join-Path $env:ProgramFiles 'nodejs\npm.cmd')
    $npmExe = $null
    foreach ($c in ($candidates | Select-Object -Unique)) {
        if (-not $c -or -not (Test-Path $c)) { continue }
        try { $probe = & $c --version 2>$null } catch { $probe = $null; $global:LASTEXITCODE = 1 }
        if ($LASTEXITCODE -eq 0 -and $probe) { $npmExe = $c; break }
    }
    if ($npmExe) {
        Write-Host "[..] installing pdf-parse (worker dependency) via $npmExe"
        & $npmExe install --prefix $tools pdf-parse --no-fund --no-audit
        if ($LASTEXITCODE -eq 0) { Write-Host "[ok] pdf-parse installed" }
        else { Write-Warning "npm install failed (exit $LASTEXITCODE). Run manually:  npm install --prefix `"$tools`" pdf-parse" }
    } else {
        Write-Warning "npm not found or not working. Run manually:  npm install --prefix `"$tools`" pdf-parse"
    }
}

# --- 4. Ollama model ---------------------------------------------------------
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Embedding model (skip if already pulled):   ollama pull bge-m3"
Write-Host "     (Ollama must be installed and running: https://ollama.com)"
Write-Host ""
Write-Host "  2. Mount the tools into DSH - add to your profile's cordis.patch.yml"
Write-Host "     (default: %USERPROFILE%\.dsh\profiles\web\cordis.patch.yml):"
Write-Host ""
Write-Host "        - insert:"
Write-Host "            - id: kb-vector-tools"
Write-Host "              name: '$(Join-Path $KbDir 'kb-plugin.mjs')'"
Write-Host ""
Write-Host "     Profiles with patchReload: live (e.g. the shipped web template) pick"
Write-Host "     this up without a restart; otherwise restart DSH."
Write-Host ""
Write-Host "  3. Verify in any DSH session:"
Write-Host '        "What is in the knowledge base?"     -> runs kb_status'
Write-Host '        "Search the codes for egress width"  -> runs kb_search'
Write-Host ""
Write-Host "  4. Add documents:"
Write-Host '        "Ingest D:\docs into the collection docs"'
