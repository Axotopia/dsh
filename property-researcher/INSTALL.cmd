@echo off
setlocal EnableExtensions
rem ============================================================================
rem INSTALL.cmd - deploy the property-researcher DSH agent preset on THIS machine
rem
rem   INSTALL.cmd        interactive (asks before overwriting an existing setup)
rem   INSTALL.cmd /Y     silent, always overwrites (good for fleet rollout)
rem
rem What it does:
rem   1. copies this package into %USERPROFILE%\.dsh\.agent-presets\property-researcher
rem      (DSH's per-user preset root - the only location presets are scanned from)
rem   2. runs a dependency install inside that server\ folder (pnpm if present,
rem      otherwise npm) so the bundled browser-tier MCP server is self-contained
rem ============================================================================

set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "DEST=%USERPROFILE%\.dsh\.agent-presets\property-researcher"
set "SRV=%DEST%\server"

echo ============================================================================
echo  property-researcher preset installer  (Property Researcher - zoning and
echo  site-feasibility research agent with adversarial code interpretation)
echo ============================================================================

rem -- sanity checks -----------------------------------------------------------
if not exist "%SRC%\server\package.json" (
    echo [ERROR] Run this script from the extracted package root ^(next to server\^).
    exit /b 1
)
if not exist "%SRC%\agent.cordis.yml" (
    echo [ERROR] agent.cordis.yml not found next to this script - package incomplete.
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
    echo An existing property-researcher install was found at the target path.
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
robocopy "%SRC%" "%DEST%" /E /NJH /NJS /NDL /NP >nul
if errorlevel 8 (
    echo [ERROR] File copy failed with robocopy code %errorlevel%.
    exit /b 1
)

rem -- install server dependencies ---------------------------------------------
echo [2/3] Installing bundled browser-tier MCP server dependencies ^(internet needed once^)...
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
    echo [WARN] Dependency installer exited with code %PKGERR%. Behind a corporate
    echo        proxy? Configure npm first:  npm config set proxy http://proxy:port
    echo        The preset still mounts without the browser tier disabled tools;
    echo        fix the dependency install, then restart DSH.
)

rem -- verify ------------------------------------------------------------------
echo [3/3] Verifying install layout...
set "FAIL="
if not exist "%DEST%\agent.cordis.yml"              set "FAIL=agent.cordis.yml missing"
if not exist "%DEST%\preset.yml"                    set "FAIL=preset.yml missing"
if not exist "%DEST%\launch-browser.cmd"            set "FAIL=launch-browser.cmd missing"
if not exist "%DEST%\plugin\mdpdf-plugin.mjs"       set "FAIL=plugin\mdpdf-plugin.mjs missing"
if not exist "%SRV%\server.js"                      set "FAIL=server\server.js missing"
if not exist "%SRV%\node_modules\puppeteer-core"    set "FAIL=node_modules incomplete (dependency install failed)"
if defined FAIL goto :failed

echo.
echo ============================================================================
echo  SUCCESS - property-researcher preset installed for %USERNAME%
echo ============================================================================
echo.
echo Next steps:
echo   1. (Optional, browser tier) Run  "%DEST%\launch-browser.cmd"
echo      to pre-start the dedicated research browser ^(CDP on port 9222,
echo      isolated profile^). The agent can also auto-start it on first need.
echo   2. In THAT browser window, log in once to any research portals you use.
echo   3. Restart the DSH app ^(or start a new session^), pick the
echo      "property-researcher" preset, and confirm tools named
echo      mcp__research-browser-pr__* appear in the session's tool list.
echo   4. Try:  Gut Check ^<address^>   for a fast screen, or paste a full
echo      feasibility question for Deep Research.
echo.
echo Uninstall anytime: delete the target folder above.
exit /b 0

:failed
echo.
echo [ERROR] Verification failed: %FAIL%
echo Fix the cause above and re-run INSTALL.cmd /Y
exit /b 1
