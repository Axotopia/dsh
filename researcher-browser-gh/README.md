# Researcher — a real-browser research agent preset for DeepSeek Harness

**Turn DeepSeek Harness Desktop (DSH) into a high-agency research agent that
drives your real browser — the visible one, logged into your portals — through
the Chrome DevTools Protocol.**

Zero-click edition: everything you need to understand, deploy, and decide is on
this page. No signup, no external links required.

> **The pitch:** DSH is already a full coding agent. Add this one folder and it
> becomes an evidence-first research agent: it navigates, clicks by visible
> text, screenshots into its own vision, extracts structured data, manages
> tabs, detects Cloudflare/Turnstile challenges, grades every claim with a
> confidence label and source URL, exports findings to PDF locally, and stops
> politely when a human check is needed. No headless bot, no browser
> downloads, no admin rights, no full-access permissions.

---

## Why your real browser, not an automation browser

Most "web agents" spin up a fresh headless/automation browser. Researcher does
the opposite — **attach-only via CDP**:

```
DSH session (preset: researcher-browser)
   │  composition row: @deepseek-ai/dsh-mcp-client (stdio)
   ▼
server/server.js   ← spawned by DSH, deps vendored in the preset folder
   │  puppeteer-core.connectOverCDP → http://127.0.0.1:9222   (ATTACH ONLY)
   ▼
The browser window you can see — dedicated profile, your real identity
```

| Automation browser | Attach-only real browser |
| --- | --- |
| Fresh fingerprint, no cookies — anti-bot systems treat it as suspicious | A real Chromium with your persisted logins — portals recognize you |
| Human must re-login everywhere, every run | Log in **once** per workstation; cookies persist in the dedicated profile |
| CAPTCHA loops you can't resolve | The agent sees the challenge, **stops**, and tells you to click it — visible window, done in seconds |
| Opaque to you | The window IS the target: what you see, the agent sees |

The server never launches a browser of its own. When no research browser is
running, the tools auto-run the packaged `launch-browser.cmd` (a visible
dedicated-profile window opens) and wait briefly for CDP. Set
`RESEARCH_AUTO_LAUNCH=0` to hand that step back to the human.

## What's in the box

- **16 browser tools** (`mcp__research-browser__*`): `browser_status`,
  `navigate`, `click` (by CSS selector **or** visible text), `type`, `scroll`,
  `back`, `forward`, `screenshot` (PNG into vision), `extract_text`
  (structured, with link labels), `html`, `wait_for`, `list_tabs`, `new_tab`,
  `switch_tab`, `close_tab`, `is_challenge`.
- **Nested iframes (cross-origin included)** and **open shadow roots**
  (`>>>` selectors) are reachable; `target=_blank` links converge back into
  the same tab; every call is time-boxed with a transparent one-shot
  reconnect.
- **`convert_md_to_pdf`** — dependency-free Markdown→PDF, rendered locally by
  headless Edge/Chrome beside the source. The only headless use in the preset;
  it never touches the network (web research stays in the visible browser).
- **Evidence protocol in the persona** — every material claim carries a source
  URL, access date, and confidence grade (`[Confirmed]`,
  `[Confirmed-as-printed]`, `⚠ UNVERIFIED(reason)`, `DEADLOCK`); conflicting
  sources are flagged, never averaged; aggregators are graded as secondary.
- **Retrieval hygiene doctrine** — pacing ≤1 request/host per 3 s,
  signature-gating before parsing, WAF/anti-bot pages treated as terminal for
  that source, one attempt per source, no TLS-verification bypass ever, and
  AV-friendly PDF extraction (single-line `node -e`, not PowerShell
  decompression pipelines).

## Requirements

- **Windows 10/11** with **DeepSeek Harness Desktop** installed (started once,
  so `%USERPROFILE%\.dsh\` exists)
- **Node.js ≥ 20** in PATH (`npm` ships with it; `pnpm` optional)
- A **Chromium-family browser**: Edge (ships with Windows), Chrome, or Brave
  (`set BROWSER=chrome` / `set BROWSER=brave` before running the launcher)
- One-time internet access during install (MCP server dependencies)

No admin rights required — everything lands under the user profile.

## Install

### Fast path

```bat
INSTALL.cmd          (interactive)
INSTALL.cmd /Y       (silent, for fleet rollout)
```

What it does: copies the preset into `%USERPROFILE%\.dsh\.agent-presets\
researcher-browser` (DSH's per-user preset root), runs `pnpm install` (falling
back to `npm install`) inside its `server\` folder, and verifies the layout.
It never touches other presets, the DSH app folder, or settings.yaml.

### Manual equivalent

```bat
xcopy /E /I /Y "<this-folder>\*" "%USERPROFILE%\.dsh\.agent-presets\researcher-browser\"
cd /d "%USERPROFILE%\.dsh\.agent-presets\researcher-browser\server"
npm install --no-audit --no-fund        (or: pnpm install)
```

**No per-machine edits are needed.** The composition derives the server
working directory from the loading user's profile at composition load time
(`!!js process.env.USERPROFILE + '/.dsh/.agent-presets/researcher-browser/server'`),
and `launch-browser.cmd` already uses `%USERPROFILE%`.

## First run

1. Restart DSH, start a session, pick the **Researcher** preset.
2. First browser tool call auto-opens the research window (or run
   `launch-browser.cmd` yourself). Verify CDP answers:
   ```powershell
   Invoke-RestMethod http://127.0.0.1:9222/json/version
   ```
   Expect JSON containing `"Browser": "Edg/..."`.
3. In THAT window, log in **once** to your SSO / research portals — cookies
   persist in the dedicated profile across restarts.
4. Ask it something navigational and confirm tools named
   `mcp__research-browser__*` appear in the session's tool list.

Example ask: *"Research 463 Glory View Ln, Manson, WA — what zone applies, what
are the dimensional standards, and what would a residential permit require?
Flag anything you couldn't verify."*

## Configuration (optional)

| Variable | Default | Meaning |
| --- | --- | --- |
| `RESEARCH_CDP_URL` | `http://127.0.0.1:9222` | DevTools endpoint the server attaches to |
| `RESEARCH_CDP_TIMEOUT_MS` | `30000` | default per-call timeout |
| `RESEARCH_AUTO_LAUNCH` | `1` (on) | `0` disables automatic running of launch-browser.cmd |
| `RESEARCH_AUTO_LAUNCH_TIMEOUT_MS` | `25000` | how long auto-start waits for CDP |

## Security model

- **Dedicated profile** at `%USERPROFILE%\.dsh\browser-profiles\research` —
  your daily browser profile is never touched (Chrome 136+ refuses remote
  debugging on default profiles anyway, so this is mandatory, not optional).
- **Loopback-only** DevTools endpoint; reachable only while that window is open.
- **Read-only research defaults** — forms, logins, purchases, downloads
  require explicit user approval.
- **Web content is untrusted data, never instructions** — imperative text in
  pages is ignored; code found in content is never executed.
- **CAPTCHA / human-verification** — the agent stops and reports
  *"Human action needed: complete the check in the browser"*, then waits.
  No aggressive retries, no bypass.
- **No TLS bypass, ever** — certificate anomalies are surfaced and routed to
  alternate official surfaces, never click-through-by-machine.

See [VALIDATION.md](VALIDATION.md) for what has been verified on this build.

---

## Development background

Researcher was built and hardened in **one agent session** — a single
conversation with a coding agent on DeepSeek Harness — then packaged for
distribution. The numbers are read live from the harness's own session log and
token meter, so they are facts, not marketing rounding:

| Metric | Value |
| --- | --- |
| Agent turns | 12 |
| Model steps (assistant messages) | 107 |
| Tool calls executed | 123 |
| LLM retries / compactions | 8 / 7 |
| Estimated cumulative session tokens | ~214K |
| Runtime model | `deepseek-v4-flash` (provider `deepseek-official`) |
| Server implementation | one 1,300-line `server.js`, plain ESM, no build step |
| Dependencies | 166 packages, vendored into the preset folder |
| Portable package | ~63 KB zip |

*(Token figure is the harness's `tokenMeter` estimator of the cumulative
session surface — context budget, not a provider invoice; DSH does not expose
an input/output token split through it.)*

One session. 123 tool calls. Zero subagents, zero browser downloads, zero
secrets — and the one thing it refused to do was execute code it found on a
web page.

### Design decisions that shaped it

1. **Attach-only beats browser automation for research.** The moment an agent
   needs your logins, CAPTCHA-passing, or anti-bot cooperation, a fresh
   automation browser loses. The visible-window model converts every anti-bot
   problem into a "you click once" problem.

2. **"Never launch a browser from the server" was the right default — until it
   wasn't.** The original spec forbade server-side launching to keep the human
   in control. The first real session hit exactly that friction, so we added
   *guarded* auto-start: it runs only the packaged launcher, opens a visible
   window, is single-flight with a cooldown, and has a `=0` kill-switch. Design
   for the operator's actual pain, then make the exception explicit and
   reversible.

3. **Endpoint protection will flag "smart" shell pipelines.** `curl -sk`
   piped into inline byte-slicing + `DeflateStream` + regex tripped Microsoft
   Defender's command-line heuristics as a false positive. The lasting fix
   wasn't a whitelist — it was retraining the *agent*: read PDFs in the browser
   or with single-line `node -e` extraction, never fetch-and-decompress in
   PowerShell, never bypass TLS validation.

4. **Banning "follow web instructions" is not enough — ban executing web
   code.** The persona treats web content as untrusted data, and additionally
   forbids executing/evaluating code found in pages, bundles, configs, or API
   responses.

5. **Session file policy ≠ plugin-spawned process capability.** The browser
   pipeline runs in the DSH-host-spawned MCP server, which the session's
   Workspace-Write sandbox does not gate. The agent's own shell/file tools are
   the confined ones — so Researcher needs no elevated permissions.

6. **Mount-validate before shipping.** Parsers validate YAML; only the harness's
   own composition audit (`standingKeyFor`) proves rows actually activate. A
   temporary probe plugin catches serverName collisions, unresolved packages,
   and never-activated rows before any user session does.

7. **Fail loudly, recoverably, and honestly.** Every failure in this session
   made the next version better: a PowerShell syntax bug (self-corrected),
   REST endpoint guesses (pivoted to the visible page), Defender blocks
   (behavior retrained), a Windows argument-quoting bug that silently ate the
   auto-start (fixed via A/B test, `windowsVerbatimArguments: true`), and
   invisible zero-width characters that corrupted a path (scrubbed with a byte
   check before release).

The full story, the FAQ, and the honest engineering lessons are in
[MARKETING.md](MARKETING.md).

---

## Repository layout

```
README.md                <- this file (install + background)
MARKETING.md             <- the zero-click explainer: pitch, FAQ, lessons learned
VALIDATION.md            <- verified capabilities + known limits
preset.yml               <- display metadata (name: Researcher)
agent.cordis.yml         <- the composition: persona + capability rows (read it — it IS the product)
launch-browser.cmd       <- dedicated CDP research browser launcher (Edge/Chrome/Brave)
INSTALL.cmd              <- one-command deploy to this machine
server/                  <- attach-only CDP/MCP bridge (16 tools; deps pinned)
  package.json
  pnpm-lock.yaml
  server.js
plugin/
  mdpdf-plugin.mjs       <- dependency-free Markdown->PDF tool (MIT, vendored)
```

## License & credits

MIT — see [LICENSE](LICENSE). The bundled `plugin/mdpdf-plugin.mjs` is derived
from `mdpdf-portable` (MIT) and adapted via
[Axotopia/dsh-property-researcher](https://github.com/Axotopia/dsh-property-researcher)
(MIT); the browser bridge shares that lineage.

**Not legal advice.** Researcher produces research support, never a substitute
for the Authority Having Jurisdiction, a surveyor, an engineer, or an attorney.
