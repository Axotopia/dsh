@echo off
setlocal EnableExtensions

rem ============================================================================
rem launch-browser.cmd - dedicated research browser for the Legal-Financial Consul
rem
rem Starts a Chromium-family browser with the Chrome DevTools Protocol enabled on
rem http://127.0.0.1:9222 so this preset's MCP server (server/server.js) can
rem ATTACH to it. The server never launches a browser of its own: run this file
rem first, OR let the server's packaged auto-launch run it for you.
rem
rem Profile: ALWAYS an isolated --user-data-dir under %USERPROFILE%\.dsh\...
rem Your daily browser profile is never touched or reused. (Chrome 136+ refuses
rem remote debugging on the default profile - the dedicated dir is mandatory.)
rem
rem SHARING NOTE: the profile dir below and port 9222 are shared with the
rem `research-swarm` / `property-researcher` / `researcher` browser tiers by
rem design, so one logged-in research browser serves them all. Do not run two
rem browser tiers on different ports, and do not point them at different
rem profiles.
rem
rem Usage:            launch-browser.cmd              (Edge, the default)
rem                   set BROWSER=chrome && launch-browser.cmd
rem                   set BROWSER=brave && launch-browser.cmd
rem ============================================================================

if /i "%BROWSER%"=="chrome" goto chrome
if /i "%BROWSER%"=="brave"  goto brave
goto :edge

:edge
set "BROWSER=edge"
set "EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
goto :go

:chrome
set "EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
goto :go

:brave
set "EXE=%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"
goto :go

:go
if not exist "%EXE%" (
    echo [legal-financial-consul] Browser executable not found: "%EXE%"
    echo [legal-financial-consul] Set BROWSER=edge^|chrome^|brave and retry.
    exit /b 1
)

set "PROFILE_DIR=%USERPROFILE%\.dsh\browser-profiles\research"
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"

start "" "%EXE%" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 "--user-data-dir=%PROFILE_DIR%" --no-first-run --no-default-browser-check

echo [legal-financial-consul] Started %BROWSER% with CDP on http://127.0.0.1:9222
echo [legal-financial-consul] Dedicated profile: "%PROFILE_DIR%"
echo [legal-financial-consul] Log in to your research portals once; sessions persist.
endlocal
exit /b 0
