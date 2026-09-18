@echo off
setlocal EnableExtensions
rem ============================================================================
rem INSTALL.cmd - deploy the Legal-Financial Consul DSH agent preset on THIS machine
rem
rem   INSTALL.cmd        interactive (asks before overwriting an existing setup)
rem   INSTALL.cmd /Y     silent, always overwrites (good for fleet rollout)
rem
rem What it does:
rem   1. copies this package into %USERPROFILE%\.dsh\.agent-presets\legal-financial-consul
rem      (DSH's per-user preset root - the only location presets are scanned from)
rem   2. runs a dependency install inside that server\ folder (pnpm if present,
rem      otherwise npm) so the bundled browser MCP server is self-contained
rem
rem The preset works WITHOUT step 2: the browser tier is an optional extra, and
rem the research swarm, Red Team, Mediator, and PDF export all work without it.
rem ============================================================================

set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "DEST=%USERPROFILE%\.dsh\.agent-presets\legal-financial-consul"
set "SRV=%DEST%\server"

echo ============================================================================
echo  legal-financial-consul preset installer  (Legal-Financial Consul - DSH)
echo ============================================================================

rem -- sanity checks -----------------------------------------------------------
if not exist "%SRC%\agent.cordis.yml" (
    echo [ERROR] Run this script from the extracted package root.
    exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js was not found in PATH. Install Node.js LTS ^>=20 first:
    echo         https://nodejs.org/  ^(npm ships with it^)
    exit /b 1
)

echo Source     : %SRC%
echo Target     : %DEST%

rem -- overwrite guard ---------------------------------------------------------
if exist "%DEST%\agent.cordis.yml" if /i not "%1"=="/Y" (
    echo.
    echo An existing legal-financial-consul install was found at the target path.
    choice /M "Overwrite it with this package" /C YN
    if errorlevel 2 (
        echo Aborted by user. Nothing was changed.
        exit /b 1
    )
)

rem -- make sure the DSH user tree exists --------------------------------------
if not exist "%USERPROFILE%\.dsh\browser-profiles" mkdir "%USERPROFILE%\.dsh\browser-profiles"

rem -- copy files --------------------------------------------------------------
echo.
echo [1/3] Copying preset files...
robocopy "%SRC%" "%DEST%" /E /NJH /NJS /NDL /NP /XD node_modules >nul
if errorlevel 8 (
    echo [ERROR] File copy failed with robocopy code %errorlevel%.
    exit /b 1
)

rem -- install server dependencies ---------------------------------------------
echo [2/3] Installing browser MCP server dependencies ^(optional, needs internet^)...
pushd "%SRV%"
where pnpm >nul 2>nul
if not errorlevel 1 (
    echo         using pnpm...
    call pnpm install
) else (
    echo         using npm ^(pnpm not found - npm works equally well here^)...
    call npm install --no-audit --no-fund
)
set "PKGERR=%errorlevel%"
popd
if not "%PKGERR%"=="0" (
    echo [WARN] Dependency installer exited with code %PKGERR%. The preset still
    echo        mounts; only the browser tier is unavailable until this succeeds.
    echo        Behind a corporate proxy? Configure npm first:
    echo          npm config set proxy http://proxy:port
)

rem -- verify ------------------------------------------------------------------
echo [3/3] Verifying install layout...
set "FAIL="
if not exist "%DEST%\agent.cordis.yml"                 set "FAIL=agent.cordis.yml missing"
if not exist "%DEST%\preset.yml"                       set "FAIL=preset.yml missing"
if not exist "%DEST%\consultation.workflow.js"         set "FAIL=consultation.workflow.js missing"
if not exist "%DEST%\launch-browser.cmd"               set "FAIL=launch-browser.cmd missing"
if not exist "%DEST%\skills\legal-financial-consul\SKILL.md" set "FAIL=SKILL.md missing"
if not exist "%DEST%\plugin\mdpdf-plugin.mjs"          set "FAIL=plugin\mdpdf-plugin.mjs missing"
if not exist "%SRV%\server.js"                         set "FAIL=server\server.js missing"
if defined FAIL goto :failed

if not exist "%SRV%\node_modules\puppeteer-core" (
    echo.
    echo [NOTE] server\node_modules is incomplete, so the browser tier will not
    echo        start. Everything else in the preset works. Re-run INSTALL.cmd /Y
    echo        online to enable it.
)

echo.
echo ============================================================================
echo  SUCCESS - legal-financial-consul preset installed for %USERNAME%
echo ============================================================================
echo.
echo Next steps:
echo   1. Start a NEW DSH session and select the "Legal-Financial Consul" preset.
echo      Confirm the tool list shows subagent / workflow / web_fetch /
echo      convert_md_to_pdf, and (if step 2 succeeded) mcp__research-browser-lfc__*.
echo   2. Optional, for gated legal portals: run "%DEST%\launch-browser.cmd"
echo      to start the dedicated research browser on port 9222, then log in once
echo      to your research portals in that window.
echo   3. Ask a structural question. The Consul will interrogate, map jurisdictions,
echo      then run the research swarm, Red Team, and Mediator.
echo.
echo Uninstall anytime: delete the target folder above.
exit /b 0

:failed
echo.
echo [ERROR] Verification failed: %FAIL%
echo Fix the cause above and re-run INSTALL.cmd /Y
exit /b 1
