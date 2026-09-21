#!/bin/sh
# ============================================================================
# launch-browser.sh - dedicated research browser for this preset (POSIX twin of
# launch-browser.cmd)
#
# Starts a Chromium-family browser with the Chrome DevTools Protocol enabled on
# http://127.0.0.1:9222 so the preset's MCP server (server/server.js) can
# ATTACH to it. The server never launches a browser itself.
#
# Profile: ALWAYS an isolated --user-data-dir under ~/.dsh/browser-profiles/.
# Your daily browser profile is never touched or reused (Chrome 136+ refuses
# remote debugging on the default profile, so the dedicated dir is mandatory).
#
# Usage:  ./launch-browser.sh                 (auto-detects an installed browser)
#         BROWSER=brave ./launch-browser.sh
#         BROWSER=chromium ./launch-browser.sh
# ============================================================================
set -eu

PROFILE_DIR="${HOME}/.dsh/browser-profiles/research"
mkdir -p "$PROFILE_DIR"

find_browser() {
  # An explicit BROWSER= wins; otherwise take the first one on PATH.
  if [ -n "${BROWSER:-}" ]; then
    command -v "$BROWSER" 2>/dev/null && return 0
    echo "[researcher-browser] BROWSER='$BROWSER' not found on PATH." >&2
    return 1
  fi
  for c in brave-browser brave chromium chromium-browser google-chrome google-chrome-stable microsoft-edge; do
    if command -v "$c" >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

EXE="$(find_browser)" || {
  echo "[researcher-browser] No Chromium-family browser found on PATH." >&2
  echo "[researcher-browser] Install one, or set BROWSER=<name> and retry." >&2
  exit 1
}

# Detach so the caller (and the MCP server's auto-launch) returns immediately.
nohup "$EXE" \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  "--user-data-dir=${PROFILE_DIR}" \
  --no-first-run \
  --no-default-browser-check \
  >/dev/null 2>&1 &

echo "[researcher-browser] Started $(basename "$EXE") with CDP on http://127.0.0.1:9222"
echo "[researcher-browser] Dedicated profile: ${PROFILE_DIR}"
echo "[researcher-browser] Log in to your research portals once; sessions persist."
