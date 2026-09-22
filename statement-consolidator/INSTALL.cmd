@echo off
setlocal EnableExtensions
rem ============================================================================
rem INSTALL.cmd - deploy the statement-consolidator DSH agent preset on THIS
rem machine.
rem
rem What it does:
rem   1. copies this package into %USERPROFILE%\.dsh\.agent-presets\
rem      statement-consolidator (DSH's per-user preset root - the only location
rem      presets are scanned from)
rem   2. reports prerequisite status (Python launcher + openpyxl) - nothing is
rem      installed automatically; warnings tell you exactly what to run
rem
rem Dependency notes:
rem   - Helper scripts need the Python standard library (csv, json, datetime,
rem     decimal, hashlib, re).
rem   - Reading .xlsx and writing the final Excel workbook BOTH need openpyxl
rem     (one install, user-scoped):  py -m pip install --user openpyxl
rem   - .csv input and .csv output work with NO third-party packages at all.
rem
rem The scripts are model-free and stdlib-based; nothing in them reads the
rem network. Keep your statement files on disk - pipeline writes outputs to
rem disk, not into the chat.
rem ============================================================================

set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "DEST=%USERPROFILE%\.dsh\.agent-presets\statement-consolidator"

echo ============================================================================
echo  statement-consolidator preset installer  (year-end statement consolidation)
echo ============================================================================

if not exist "%SRC%\agent.cordis.yml" (
    echo [ERROR] Run this script from the package root ^(^next to agent.cordis.yml^).
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
    echo [WARN] Python launcher 'py' not found on Windows, 'python3' not on PATH on
    echo        Linux/macOS. Install Python 3.x (3.10+) to run the helper scripts.
) else (
    py -c "import openpyxl" >nul 2>nul
    if errorlevel 1 (
        echo [WARN] openpyxl missing - XLSX reading + final workbook output need it:
        echo          py -m pip install --user openpyxl
        echo        (CSV input / CSV output does NOT need it.)
    )
)

rem -- verify the bundled skill is discoverable --------------------------------
if exist "%DEST%\skills\statement-consolidation\SKILL.md" (
    echo [OK] bundled skill 'statement-consolidation' present
) else (
    echo [WARN] bundled skill SKILL.md MISSING - the persona will not be able to load
    echo        its protocol. Re-copy the package or check %SRC%\skills
)

echo.
echo Done. Pick the "Statement Consolidator" preset in the DSH GUI and point it at a
echo folder of CSV/XLSX statements. For a new institution the agent will propose the
echo mapping and ask for ONE confirmation; after that every later statement from that
echo institution maps automatically. Save mappings in <workspace>\mappings\ so they
echo survive across sessions.
exit /b 0
