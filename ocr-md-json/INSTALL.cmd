@echo off
setlocal EnableExtensions
rem ============================================================================
rem INSTALL.cmd - deploy the ocr-md-json DSH agent preset on THIS machine
rem
rem What it does:
rem   1. copies this package into %USERPROFILE%\.dsh\.agent-presets\ocr-md-json
rem      (DSH's per-user preset root - the only location presets are scanned from)
rem   2. reports prerequisite status (Python launcher + Pillow) - nothing is
rem      installed automatically; warnings tell you exactly what to run
rem
rem Notes:
rem   - The helper scripts are model-free: extract_pdf_text.py / dedupe.py /
rem     md_tables_to_json.py need only the Python standard library;
rem     extract_pdf_images.py additionally needs Pillow (PNG conversion).
rem   - The image route needs a VISION-CAPABLE session model (the persona detects
rem     a missing read_image route and falls back to text-only sources) and the
rem     DSH delegation tools (subagent) for the parallel vision fan-out.
rem ============================================================================

set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "DEST=%USERPROFILE%\.dsh\.agent-presets\ocr-md-json"

echo ============================================================================
echo  ocr-md-json preset installer  (PDF/photo consolidation to MD + JSON tables)
echo ============================================================================

if not exist "%SRC%\agent.cordis.yml" (
    echo [ERROR] Run this script from the package root ^(next to agent.cordis.yml^).
    exit /b 1
)

robocopy "%SRC%" "%DEST%" /E /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
    echo [ERROR] robocopy failed with code %errorlevel%
    exit /b 1
)
echo [OK] preset copied to %DEST%

rem -- prerequisite report (warn only - nothing auto-installed) ----------------
where py >nul 2>nul
if errorlevel 1 (
    echo [WARN] Python launcher 'py' not found - all helper scripts need it: install Python 3.x
) else (
    py -c "import PIL" >nul 2>nul
    if errorlevel 1 echo [WARN] Pillow missing - image-PDF extraction needs it: py -m pip install --user Pillow
)

echo.
echo Done. Pick the "OCR-MD-JSON" preset in the DSH GUI and point it at a source
echo folder; the persona stages a copy into the session workspace and consolidates.
exit /b 0
