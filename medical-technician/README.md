# medical-technician

**The Integrative Causal Architect (V6.0) deployed on [DeepSeek Harness (DSH)](https://github.com/Axotopia/dsh) Research Swarm infrastructure — a medical-analyst preset that builds life-input → biological-output causal models, pressure-tests them adversarially, and critiques standard-of-care with evidence tiers, using the swarm's parallel subagent/workflow/ralph plane and its real-browser research tier.**

`medical-technician` is the [`research-swarm`](../research-swarm) preset with the **V6.0 SYSTEM PROMPT: THE INTEGRATIVE CAUSAL ARCHITECT** infused into its persona. The V6.0 text is the analytical constitution (mandatory construction phases, evidence tiering 1–5, multi-framework analysis, SOC gap analysis, quality gates); the swarm layer supplies the operations: live web verification, browser research, parallel fan-out, and adversarial review passes.

The persona combines two planes:

- **The V6.0 analytical plane** — a structured, evidence-tiered causal-modeling discipline: complete input matrix (Diet, Environment, Time, Trauma, Toxin, Thought, Pharmacological, Microbial), multi-framework analysis (mechanistic reductionism, evolutionary medicine, non-Western traditions, systems biology), a Bayesian mechanism map, competing-model construction, function-vs-pathology framing, adversarial pressure-testing, standard-of-care gap analysis, sourcing & bias reporting, a defining experiment, and a known-unknowns register. Fifteen quality gates and a strict **clinical boundary condition**: literature-based analytical hypotheses for clinical discussion — never personalized medical directives.
- **The swarm operations plane** — the research-swarm orchestration rules: parallel subagent fan-out, `workflow` scripts, fresh-agent `ralph` rounds, an evidence protocol with confidence grades, retrieval hygiene, an untrusted-data rule for web content, CAPTCHA stop-and-report behavior, and an adversarial blue/red cross-check that runs *as subagents* — so verification itself fans out.

Both planes share one **real-browser research tier**: a dedicated-profile Chromium driven over the Chrome DevTools Protocol, with a queue-hardened MCP server that many concurrent agents can safely share.

---

> ## ⚠️ Research prototype — not medical advice
>
> **`medical-technician` is a research prototype only.** It is not a medical device,
> not a licensed clinician, and not a substitute for professional medical care.
>
> Everything this preset produces is **literature-based analytical hypothesis for
> clinical discussion — it is NOT medical advice**. It does not diagnose, treat,
> or prescribe, and it cannot account for your full clinical picture.
>
> **Always consult a qualified healthcare professional before making any
> health-related decision.** The preset is bound to end every material output
> with this disclaimer and to never present its output as a substitute for
> professional care — but you remain responsible for how you use its output.
>
> Do not use this preset, or any of its output, in any patient-facing,
> clinical, diagnostic, or treatment context.

---

## What's inside

| File | Purpose |
|---|---|
| `agent.cordis.yml` | The agent-plane composition: persona = **V6.0 Integrative Causal Architect** + swarm operations layer; plus delegation/workflows, plan mode, compaction, goals, skills, shell tools, the MCP browser bridge, and the Markdown→PDF plugin. |
| `preset.yml` | Preset metadata (`name: Medical Technician`). |
| `launch-browser.cmd` | Starts the dedicated research browser (Edge by default; `chrome` / `brave` via `BROWSER`) with CDP enabled on `127.0.0.1:9222` and an isolated profile under `%USERPROFILE%\.dsh\browser-profiles\research`. |
| `server/server.js` | The research-browser MCP server — attach-only CDP tools, **FIFO-serialized for multi-agent sharing**. Registers as serverName `medical-technician` (unique in the DSH process; `researcher` reserves `research-browser`, `research-swarm` reserves `research-swarm2`). |
| `server/package.json`, `server/pnpm-lock.yaml` | Server dependencies (pinned lockfile). `node_modules/` is produced on install and is deliberately not distributed. |
| `plugin/mdpdf-plugin.mjs` | `convert_md_to_pdf` — dependency-free local Markdown→PDF renderer (headless Edge/Chrome `--print-to-pdf`, never touches the network). |

## The V6.0 infusion

The persona text is structured in two layers:

1. **V6.0 SYSTEM PROMPT: THE INTEGRATIVE CAUSAL ARCHITECT** — reproduced verbatim: role definition & epistemic positioning, mandatory construction phases (input matrix → multi-framework analysis → Bayesian mechanism map → competing models → function-vs-pathology → pressure testing → SOC gap analysis → cross-epistemic tensions → sourcing & bias report → defining experiment → known unknowns), the 15 quality gates, and the ultimate validation question.
2. **DEPLOYMENT LAYER — SWARM OPERATIONS & TOOL DISCIPLINE** — the research-swarm operational rules: orchestration, research rules, the browser tier (`mcp__medical-technician__*`), evidence protocol, retrieval hygiene, PDF/binary extraction, adversarial cross-check, and the ocr-md pipeline.

**One explicit override (documented in the persona):** the V6.0 text says "You cannot perform live database queries — rely on the depth of your pre-trained knowledge." That clause was written for a bare-LLM deployment; this preset genuinely provides live `web_search` and a real browser. The deployment layer therefore instructs the agent to use live verification where possible and to label every claim's provenance (live-verified → URL + access date + confidence grade; pre-training-only → explicitly labeled), while never claiming to have queried a database it did not query — preserving the V6.0 transparency mandate.

## The browser tier — 16 tools, one shared browser

The MCP server registers as serverName `medical-technician`, so the model sees `mcp__medical-technician__*`:

`browser_status`, `navigate`, `click`, `type`, `scroll`, `back`, `forward`, `screenshot`, `extract_text`, `html`, `wait_for`, `list_tabs`, `new_tab`, `switch_tab`, `close_tab`, `is_challenge`

Design rules (unchanged from research-swarm):

- **Attach-only.** The server never launches or automates a browser of its own; it connects over CDP to the dedicated browser started by `launch-browser.cmd`. When the endpoint is unreachable it runs the packaged launcher automatically (disable with `RESEARCH_AUTO_LAUNCH=0`).
- **One visible, dedicated-profile window.** Your daily browser profile is never touched (Chrome 136+ requires a dedicated `--user-data-dir` for remote debugging anyway).
- **Read-only research defaults.** Forms, logins, purchases, downloads, and any remote modification require explicit user approval; the persona carries the same rule.
- **FIFO-serialized calls** — every agent joined to the preset shares one MCP server process and one browser; all tool calls go through a single queue so parallel agents can observe the browser but never interleave mid-action on it.
- **Scout-only browsing.** There is no per-call tab addressing — every page tool acts on one shared active tab — so the persona directs all browser work through ONE designated browser-scout workstream at a time; other children queue behind it.

## Install

**Via DSH self-serve (recommended):** in any DSH session, point it at this folder:

> "Install the agent preset at https://github.com/Axotopia/dsh/tree/main/medical-technician, install any dependencies it needs, and verify it mounts. Grant Full Access to the filesystem for this job."

Notes: **Full Access is needed only because the preset lands *outside* the session workspace** (`%USERPROFILE%\.dsh\.agent-presets\`). The research/analysis work itself runs under fixed, non-escalating scope. There are no model dependencies to configure: all model traffic goes through your existing DSH provider settings. Approve any prompts the agent raises, and add missing provider keys in Settings → Models if a session reports a failed seat.

**Manual (Windows):**

1. Copy this folder to `%USERPROFILE%\.dsh\.agent-presets\medical-technician` (the folder name is the preset id — keep it `medical-technician`).
2. Install server dependencies (produces a self-contained `node_modules` — nothing global is touched):
   ```
   cd %USERPROFILE%\.dsh\.agent-presets\medical-technician\server
   pnpm install
   ```
3. Restart the DSH host and create a session on the `medical-technician` preset.

**Requirements:** Windows 10/11 (the launcher is a `.cmd` batch file), a recent DSH build carrying the `@deepseek-ai/*` plugin set, Node.js ≥ 20, pnpm 10+, and Microsoft Edge (default) / Chrome / Brave.

**Model requirements: vision is optional.** The research loop is text-first — `navigate`, `click` (CSS or visible text), `extract_text`, `html`, tab management, and `is_challenge` (DOM-text signature scanning, not pixel analysis) all work with a text-only model. The one vision-dependent tool is `screenshot`; on text-only routes it degrades to a placeholder — simply skip it. Measurements always come from page data, never pixels (evidence protocol).

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
- **One shared active tab.** Browser work is deliberately serialized through one scout; heavy parallel browsing of *different* sites should go through `web_search` plus local synthesis.
- **Shared CDP port across presets.** The port `9222` and the profile directory are shared with the `researcher`/`research-swarm` browser tiers by design; do not run two browser tiers on the same port concurrently.
- **Queue latency.** With many agents queued behind a long call, callers can observe client-side timeouts; the queue drains, but calls are not cancelled server-side.

## Provenance & credits

- Composition derived from the [`research-swarm`](../research-swarm) preset (itself derived from the [`researcher`](../researcher) preset) with the V6.0 Integrative Causal Architect prompt infused into the persona and the MCP server renamed to `medical-technician`.
- V6.0 prompt authored by the preset owner (user-supplied); reproduced verbatim in `agent.cordis.yml`.
- `plugin/mdpdf-plugin.mjs` is vendored from [Axotopia/dsh-property-researcher](https://github.com/Axotopia/dsh) (MIT).
- The MCP server vendors only `puppeteer-core` and `@modelcontextprotocol/sdk` (see `server/pnpm-lock.yaml`).

## License

MIT — see `LICENSE`. Provided as a **research prototype**: review the composition (`agent.cordis.yml`), the persona, and the tool integrations before any use. The preset is an analytical tool for literature-based research and does not provide medical advice; its output is not a diagnosis, treatment plan, or clinical directive, and a qualified healthcare professional should always be consulted for any health-related decision. See the disclaimer at the top of this README.
