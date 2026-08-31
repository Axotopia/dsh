# research-swarm

**A KIMI-style agent-swarm orchestrator fused with a high-agency, evidence-discipline research kit for [DeepSeek Harness (DSH)](https://github.com/Axotopia/dsh) — parallel subagent fan-out, workflow and fresh-agent iteration, and a real-browser research tier that is hardened for many agents sharing one browser.**

`research-swarm` is one preset that combines two disciplines that usually live apart:

- **The swarm plane** — a full coding-agent composition plus KIMI-style orchestration: `subagent` / `subagent_fork` delegation, `workflow` scripts with `parallel()` / `pipeline()` fan-out, and `ralph` fresh-agent rounds with the shared workspace as durable memory.
- **The research plane** — an evidence protocol with confidence grades, retrieval hygiene, an untrusted-data rule for web content, CAPTCHA stop-and-report behavior, and an adversarial blue/red cross-check that runs *as subagents* — so verification itself fans out.

Both planes share one **real-browser research tier**: a dedicated-profile Chromium driven over the Chrome DevTools Protocol, with a queue-hardened MCP server that many concurrent agents can safely share.

---

## What's inside

| File | Purpose |
|---|---|
| `agent.cordis.yml` | The agent-plane composition (19 rows): persona, delegation/workflows, plan mode, compaction, goals, skills, shell tools, the MCP browser bridge, and the Markdown→PDF plugin. |
| `preset.yml` | Preset metadata (`name: Research Swarm`). |
| `launch-browser.cmd` | Starts the dedicated research browser (Edge by default; `chrome` / `brave` via `BROWSER`) with CDP enabled on `127.0.0.1:9222` and an isolated profile under `%USERPROFILE%\.dsh\browser-profiles\research`. |
| `server/server.js` | The research-browser MCP server — attach-only CDP tools, **FIFO-serialized for multi-agent sharing**. |
| `server/package.json`, `server/pnpm-lock.yaml` | Server dependencies (pinned lockfile). `node_modules/` is produced on install and is deliberately not distributed. |
| `plugin/mdpdf-plugin.mjs` | `convert_md_to_pdf` — dependency-free local Markdown→PDF renderer (headless Edge/Chrome `--print-to-pdf`, never touches the network). |

## The browser tier — 16 tools, one shared browser

The MCP server registers as serverName `research-swarm`, so the model sees `mcp__research-swarm__*`:

`browser_status`, `navigate`, `click`, `type`, `scroll`, `back`, `forward`, `screenshot`, `extract_text`, `html`, `wait_for`, `list_tabs`, `new_tab`, `switch_tab`, `close_tab`, `is_challenge`

Design rules:

- **Attach-only.** The server never launches or automates a browser of its own; it connects over CDP to the dedicated browser started by `launch-browser.cmd`. When the endpoint is unreachable it runs the packaged launcher automatically (disable with `RESEARCH_AUTO_LAUNCH=0`).
- **One visible, dedicated-profile window.** Your daily browser profile is never touched (Chrome 136+ requires a dedicated `--user-data-dir` for remote debugging anyway).
- **Read-only research defaults.** Forms, logins, purchases, downloads, and any remote modification require explicit user approval; the persona carries the same rule.

## Multi-agent hardening

Every agent joined to this preset (the orchestrator and all spawned children) shares **one** MCP server process and **one** browser. Three mechanisms make that safe:

1. **FIFO queue.** All tool calls are serialized through a single promise-chain queue (`enqueueToolCall`): strictly one call executes at a time, a failed call never clogs the chain, and every handler path is time-boxed — so parallel agents can observe the browser but never interleave mid-action on it.
2. **Tab guard.** `click` snapshots the open-page set before clicking and only treats pages *created by the click* as popups — a link click can never close a pre-existing tab (including another agent's).
3. **Scout-only browsing.** There is no per-call tab addressing: every page tool acts on one shared active tab. The persona therefore directs all browser work through ONE designated browser-scout workstream at a time (or the orchestrator itself between dispatches); other children must not call browser tools and queue browsing needs behind the current scout. `web_search`-heavy and local-synthesis workstreams still fan out freely.

This hardening was added after a red-team audit of the single-agent `researcher` design and covers queue bypass, slot leaks, synchronous throws, cancellation, and cross-agent tab damage.

## Install

**Via DSH self-serve (recommended):** in any DSH session, point it at this folder:

> "Install the agent preset at https://github.com/Axotopia/dsh/tree/main/research-swarm, install any dependencies it needs, and verify it mounts."

**Manual (Windows):**

1. Copy this folder to `%USERPROFILE%\.dsh\.agent-presets\research-swarm` (the folder name is the preset id — keep it `research-swarm`).
2. Install server dependencies (produces a self-contained `node_modules` with junctions into the preset's own store — nothing global is touched):
   ```
   cd %USERPROFILE%\.dsh\.agent-presets\research-swarm\server
   pnpm install
   ```
3. Restart the DSH host and create a session on the `research-swarm` preset.

**Requirements:** Windows 10/11 (the launcher is a `.cmd` batch file), a recent DSH build carrying the `@deepseek-ai/*` plugin set, Node.js ≥ 20 (DSH's bundled Node works), pnpm 10+, and Microsoft Edge (default) / Chrome / Brave.

**First run:** call `browser_status`. If the browser is not running, the tools start it automatically — a visible dedicated-profile window opens. Log in to your research portals once; sessions persist in the dedicated profile.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `RESEARCH_CDP_URL` | `http://127.0.0.1:9222` | CDP endpoint the server attaches to. |
| `RESEARCH_CDP_TIMEOUT_MS` | `30000` | Per-call wait budget (clamped 5,000–300,000). |
| `RESEARCH_AUTO_LAUNCH` | enabled | Set `0` to disable automatic `launch-browser.cmd` starts. |
| `RESEARCH_AUTO_LAUNCH_TIMEOUT_MS` | `25000` | How long to poll CDP after an automatic start. |
| `BROWSER` | `edge` | Launcher browser: `edge` \| `chrome` \| `brave`. |

## Markdown → PDF

`convert_md_to_pdf` renders Markdown files to PDF **locally** beside the source: built-in Markdown→HTML, then headless Edge/Chrome `--print-to-pdf` in a throwaway profile. It consumes the host `fs` / `subprocess` / `sandboxPolicy` services, publishes no services itself, and never touches the network. This is the only headless-browser use in the preset.

## Security posture

- Loopback-only CDP (`127.0.0.1:9222`), dedicated browser profile, no TLS-verification bypass anywhere.
- Web content is treated as untrusted data, never instructions; no execution of web-discovered code in any shell or tool.
- No credentials in prompts, tool calls, or files; CAPTCHA/human-verification challenges stop and surface "Human action needed" instead of retrying or evading.
- The PDF doctrine uses a single-line `node -e` (`fs` + `zlib.inflateSync`) instead of PowerShell decompression pipelines, which endpoint protection commonly flags.
- All `!!js` expressions in the composition are limited to `process.platform` comparisons and a `process.env.USERPROFILE` path concat — evaluated at composition load, nothing else.

## Known limitations

- **Windows-first.** The browser launcher is a Windows batch file; POSIX deployments need a small shell adaptation.
- **One shared active tab.** Browser work is deliberately serialized through one scout; heavy parallel browsing of *different* sites should go through `web_search` plus local synthesis, or additional presets/instances.
- **Shared CDP port across presets.** The port `9222` and the profile directory are shared with the `researcher` preset's browser tier by design; running both presets' browser tiers concurrently means two independent server processes on one browser — avoid that, or change `RESEARCH_CDP_URL`/the profile for one of them.
- **Queue latency.** With many agents queued behind a long call (e.g. a slow navigation on an iframe-heavy page), callers can observe client-side timeouts; the queue drains, but calls are not cancelled server-side.

## Provenance & credits

- Derived from the [`researcher`](../researcher) preset (real-browser CDP research tier, evidence persona), with the swarm orchestration plane, the multi-agent queue/tab hardening, and the `research-swarm` serverName added so both presets can coexist in one DSH process (`researcher` reserves `research-browser`).
- `plugin/mdpdf-plugin.mjs` is vendored from [Axotopia/dsh-property-researcher](https://github.com/Axotopia/dsh) (MIT; originally the dependency-free `mdpdf-portable` preset).
- The MCP server vendors only `puppeteer-core` and `@modelcontextprotocol/sdk` (see `server/pnpm-lock.yaml`).

## License

MIT — see the repository license. Provided as a proof of concept: review the composition (`agent.cordis.yml`), the persona, and the tool integrations before production use.
