@echo off
setlocal EnableExtensions

rem ============================================================================
rem launch-browser.cmd - dedicated research browser for the Researcher preset
rem
rem Starts a Chromium-family browser with the Chrome DevTools Protocol enabled
rem on http://127.0.0.1:9222 so the preset's MCP server (server/server.js) can
rem ATTACH to it. The server never launches a browser; run this file first.
rem
rem Profile: ALWAYS an isolated --user-data-dir under %USERPROFILE%\.dsh\...
rem Your daily browser profile is never touched or reused. (Chrome 136+
rem refuses remote debugging on the default profile - the dedicated dir is
rem mandatory, not optional.)
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
    echo [researcher-browser] Browser executable not found: "%EXE%"
    echo [researcher-browser] Set BROWSER=edge^|chrome^|brave and retry.
    exit /b 1
)

set "PROFILE_DIR=%USERPROFILE%\.dsh\browser-profiles\research"
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"

start "" "%EXE%" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 "--user-data-dir=%PROFILE_DIR%" --no-first-run --no-default-browser-check

echo [researcher-browser] Started %BROWSER% with CDP on http://127.0.0.1:9222
echo [researcher-browser] Dedicated profile: "%PROFILE_DIR%"
echo [researcher-browser] Log in to your research portals once; sessions persist.
endlocal
exit /b 0
