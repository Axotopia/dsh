@echo off
setlocal EnableExtensions
rem ============================================================================
rem INSTALL.cmd - deploy the researcher-browser DSH agent preset on THIS machine
rem
rem   INSTALL.cmd        interactive (asks before overwriting an existing setup)
rem   INSTALL.cmd /Y     silent, always overwrites (good for fleet rollout)
rem
rem What it does:
rem   1. copies this package into %USERPROFILE%\.dsh\.agent-presets\researcher-browser
rem      (DSH's per-user preset root - the only location presets are scanned from)
rem   2. runs a dependency install inside that server\ folder (pnpm if present,
rem      otherwise npm) so the MCP server is self-contained
rem ============================================================================

set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "DEST=%USERPROFILE%\.dsh\.agent-presets\researcher-browser"
set "SRV=%DEST%\server"

echo ============================================================================
echo  researcher-browser preset installer  (Researcher - DSH research agent)
echo ============================================================================

rem -- sanity checks -----------------------------------------------------------
if not exist "%SRC%\server\package.json" (
    echo [ERROR] Run this script from the extracted package root ^(next to server\^).
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
    echo An existing researcher-browser install was found at the target path.
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
echo [2/3] Installing MCP server dependencies ^(this needs internet access once^)...
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
)

rem -- verify ------------------------------------------------------------------
echo [3/3] Verifying install layout...
set "FAIL="
if not exist "%DEST%\agent.cordis.yml"              set "FAIL=agent.cordis.yml missing"
if not exist "%DEST%\preset.yml"                    set "FAIL=preset.yml missing"
if not exist "%DEST%\launch-browser.cmd"            set "FAIL=launch-browser.cmd missing"
if not exist "%SRV%\server.js"                      set "FAIL=server\server.js missing"
if not exist "%SRV%\node_modules\puppeteer-core"    set "FAIL=node_modules incomplete (dependency install failed)"
if defined FAIL goto :failed

echo.
echo ============================================================================
echo  SUCCESS - researcher-browser preset installed for %USERNAME%
echo ============================================================================
echo.
echo Next steps:
echo   1. Run  "%DEST%\launch-browser.cmd"  to start the dedicated
echo      research browser ^(CDP on port 9222, isolated profile^).
echo   2. In THAT browser window, log in once to your SSO/research portals.
echo   3. Restart the DSH app ^(or start a new session^), pick the
echo      "Researcher" preset, and confirm tools named mcp__research-browser__*
echo      appear in the session's tool list.
echo.
echo Uninstall anytime: delete the target folder above.
exit /b 0

:failed
echo.
echo [ERROR] Verification failed: %FAIL%
echo Fix the cause above and re-run INSTALL.cmd /Y
exit /b 1
