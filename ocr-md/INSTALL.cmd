@echo off
setlocal EnableExtensions
rem ============================================================================
rem INSTALL.cmd - deploy the ocr-md DSH agent preset on THIS machine
rem
rem What it does:
rem   1. copies this package into %USERPROFILE%\.dsh\.agent-presets\ocr-md
rem      (DSH's per-user preset root - the only location presets are scanned from)
rem   2. reports prerequisite status (Ollama, Python + pypdfium2) - nothing is
rem      installed automatically; warnings tell you exactly what to run
rem
rem After install: pull the ladder models named in ocr.config.json / README.md,
rem e.g.  ollama pull glm-ocr:bf16   (plus your machine's verifier tier).
rem ============================================================================

set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "DEST=%USERPROFILE%\.dsh\.agent-presets\ocr-md"

echo ============================================================================
echo  ocr-md preset installer  (verified OCR to Markdown - images and PDFs)
echo ============================================================================

if not exist "%SRC%\ocr.ps1" (
    echo [ERROR] Run this script from the package root ^(next to ocr.ps1^).
    exit /b 1
)

if not exist "%DEST%" mkdir "%DEST%"
copy /Y "%SRC%\preset.yml"       "%DEST%\" >nul
copy /Y "%SRC%\agent.cordis.yml" "%DEST%\" >nul
copy /Y "%SRC%\ocr.config.json"  "%DEST%\" >nul
copy /Y "%SRC%\ocr.ps1"          "%DEST%\" >nul
copy /Y "%SRC%\pdf_pages.py"     "%DEST%\" >nul
copy /Y "%SRC%\README.md"        "%DEST%\" >nul
echo [OK] preset copied to %DEST%

rem -- prerequisite report (warn only - nothing auto-installed) ----------------
where py >nul 2>nul
if errorlevel 1 (
    echo [WARN] Python launcher 'py' not found - PDF support needs it: install Python 3.x
) else (
    py -c "import pypdfium2" >nul 2>nul
    if errorlevel 1 echo [WARN] pypdfium2 missing - PDFs need it: py -m pip install --user pypdfium2
)
curl -s -o NUL http://127.0.0.1:11434/ 2>nul
if errorlevel 1 echo [WARN] Ollama not reachable at http://127.0.0.1:11434 - start it and pull the ladder models (see README.md)

echo.
echo Done. The researcher preset routes image/PDF extraction here automatically.
echo Verify: run any DSH session on the OCR to Markdown preset, or call ocr.ps1 directly.
exit /b 0
