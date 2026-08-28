# VALIDATION — researcher-browser preset

What has been verified on this deployment (DeepSeek Harness Desktop, Windows,
Node v24.13.0, Edge 151, pnpm 11.7). Field evidence from the build session
: 12 turns, 107 model steps, 123 tool calls.

## Verified capabilities

| Capability | Evidence |
|---|---|
| Preset mounts | `agentPresets.standingKeyFor('researcher-browser')` via a temporary probe plugin — composition composed cleanly, MCP-client row activated (this deployment: `serverName` is process-global across standing mounts, so re-validating the same preset twice in one process collides by design — validated once per process lifetime or via uniquely-named throwaway copies) |
| MCP surface | Full stdio handshake (`initialize` → `tools/list` → live `tools/call`): 16 browser tools enumerated and one real `browser_status` call attached over CDP |
| CDP attach | `launch-browser.cmd` → `http://127.0.0.1:9222/json/version` answers; `browser_status` returns `connected:true`, tab count, titles |
| Automatic start | Browser force-killed, then a single `browser_status` call spawned the packaged launcher, CDP answered in ~1 s, tool returned `connected:true`. Fix history: the spawn requires `windowsVerbatimArguments: true` — proven by A/B diagnostic (plain quoting "succeeds" silently) |
| Portability | `cwd` derived at load time from `process.env.USERPROFILE` (`!!js`) — evaluated to an existing directory containing `server.js`; a renamed probe copy (unique `serverName`) mounted under the real loader; deployed and portable compositions row-identical; zero machine-specific paths, zero invisible (zero-width) characters |
| Dependencies | `pnpm install` vendored 166 packages into the preset folder; `node_modules` deliberately excluded from the portable zip (produced on install); zip = 51.9 KB |
| Distribution | `INSTALL.cmd` (and `/Y` silent) copies into `%USERPROFILE%\.dsh\.agent-presets\researcher-browser`, installs server deps, verifies layout; README + HIGH-AGENCY-RESEARCHER.md travel in the package |
| Endpoint-protection interplay | PowerShell fetch→decompress→regex pipelines tripped Microsoft Defender (false positive, "malicious command line"); doctrine moved PDF text extraction to single-line `node -e` (`fs` + `zlib.inflateSync`) or browser rendering; TLS-bypass flags banned outright; no whitelisting required |
| Security posture | Loopback-only DevTools, dedicated profile (`%USERPROFILE%\.dsh\browser-profiles\research`), read-only research defaults, CAPTCHA stop-and-report, web content treated as untrusted data, no execution of web-discovered code |

## Known limits

- Windows-first: `launch-browser.cmd` and `INSTALL.cmd` are batch scripts; POSIX
  deployments need a small shell-script adaptation (documented in README).
- The browser tier requires a visible window; fully headless web research is
  deliberately unsupported. Headless use exists only inside the local
  Markdown→PDF renderer (`convert_md_to_pdf`), which never touches the network.
- Session token figures come from DSH's `tokenMeter` (an estimator of the
  session surface); DSH does not expose an input/output token split through it.
- The `mdpdf-plugin.mjs` tool is vendored from `Axotopia/dsh-property-researcher`
  (MIT, originally `mdpdf-portable`); local-render behavior was verified on this
  machine via the same headless Edge pipeline the plugin invokes.
