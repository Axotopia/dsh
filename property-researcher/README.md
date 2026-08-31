# AEC/RE Sector Property Researcher

**A DeepSeek Harness (DSH) agent preset for property due diligence** — multi-agent
zoning, permitting & site-feasibility research with adversarial code interpretation,
an enforced citation protocol, and a real-browser retrieval tier.

Ask it about a parcel and a proposed development; get back a **graded, cited
feasibility answer** — what zone actually applies (with the ordinance number and
effective date), the dimensional standards that will be enforced (quoted verbatim
from the operative code chapter), critical-areas and overlay hits, the full
compliance map across agencies, a cost envelope, and an honest list of what could
*not* be verified and exactly how to close each gap.

> **Not legal advice.** Outputs are research support for licensed professionals,
> buyers, and developers — never a substitute for the AHJ, a surveyor, an engineer,
> or an attorney. Every generated document says so.

---

## Why it's different

Most AI property tools answer from a search index. This one treats **records as
evidence**:

- **Evidence grading on every claim** — `[Confirmed]` (fetched this session, quote
  attached, access date recorded), `[Confirmed-as-printed]` (the record says so;
  currency not established), `⚠ UNVERIFIED(reason)`, and **DEADLOCK** for questions
  that survive every source class — declared openly, with the phone call or records
  request that closes them.
- **Verbatim code, operative versions** — dimensional standards are quoted from the
  governing code with section cites; a zone label from an assessor card or aggregator
  is *never* trusted over the jurisdiction's own GIS/city record.
- **Adversarial interpretation** — Deep Research runs Blue/Red teams over the
  harvest and a Neutral Arbiter that must reconcile them against verbatim text
  (it has caught stale interim-law analysis and rebutted "threshold killer"
  framings with the actual nonconforming-lot provision).
- **Real-browser retrieval** — when a code republication or permit portal 403s
  plain fetches, the agent attaches (Chrome DevTools Protocol) to a visible,
  dedicated-profile browser you can watch, renders the page, and quotes it — while
  CAPTCHAs and logins stop it dead for human action rather than bypassing anything.
- **Honest nulls** — a blank is always better than a guess; every gap is named,
  graded, and paired with its resolution path.

## Two modes

| | **Gut Check** | **Deep Research** |
|---|---|---|
| Purpose | Fast screen — is deeper research warranted? | Client-ready feasibility report |
| Shape | Single model, one continuous turn | Harvester fan-out → Blue/Red teams → Neutral Arbiter |
| Budget | ≤8 retrieval calls in known jurisdictions, ≤14 in unknown ones (ledger-disclosed) | Unbounded, fully itemized ledger |
| Output | `gut_check_<street>.md` | `final_report_<street>.md` + BIM JSON payload |

Both render the complete document in chat, save it to the workspace, and offer a
client-distribution PDF (rendered locally via headless Edge/Chrome — no cloud).

## The retrieval ladder

1. **Signature-gated direct fetch** — every response's file signature is validated
   before trust; pacing ≤1 request/host per 3 s; WAF challenge pages are terminal,
   never brute-forced.
2. **Structured data / official APIs** — city open-data portals, ArcGIS REST
   point-queries, county GIS layers. JSON beats pixels.
3. **Browser attach** — for JS-rendered or bot-walled surfaces (code
   republications, permit portals, auditor document viewers).

Jurisdiction doctrine: **source authority follows incorporation** — an incorporated
city's own portal/GIS governs city parcels; unincorporated land falls to county
systems; county assessor labels are never trusted for zone currency. Unknown
jurisdictions trigger a discovery ladder before any analysis.

## Requirements

- **Windows** with **DSH** (DeepSeek Harness) installed — tested on 0.1.1-rc.2
- **Node.js ≥ 20** in PATH (`npm` ships with it; `pnpm` optional). This is a
  genuine requirement, not a formality: DSH spawns the preset's MCP server as a
  **separate** `node` process resolved from PATH, so Node must be installed
  even though DSH itself runs on a Node runtime.
- A **Chromium-family browser** (Edge ships with Windows) — browser tier + PDF rendering
- One-time internet access on install (MCP server dependencies)

**Python is not required.** The entire stack is JavaScript (server, plugin) and
batch files (launcher/installer); `puppeteer-core` does not download a browser
either. No admin rights required — everything lands under the user profile.

**Vision is optional.** A vision-capable multimodal LLM is not required. The
retrieval loop is text-first — navigate, click (CSS or visible text),
extract_text, html, tab management, and challenge detection (DOM-text
signatures, not pixel analysis) all work with a text-only model, and DSH
automatically replaces image content with a text placeholder on routes declared
text-only. The one vision-dependent tool is `screenshot` (PNG image content):
on a text-only model it degrades to that placeholder, so just skip it.
Vision-capable models can use `screenshot` for layout sanity checks — evidence
still comes from quoted page text, never pixels.

### Installing Node.js (Windows 11)

Property Researcher needs a Node.js **LTS** release (v20 or newer) in PATH.
Two easy ways:

- **Recommended — winget** (ships with Windows 11). In a terminal:
  ```bat
  winget install OpenJS.NodeJS.LTS
  ```
- **Manual** — go to <https://nodejs.org>, download the **LTS** installer
  (`.msi`), run it, and keep the default options (it adds Node to PATH and
  installs `npm` for you).

Verify either way by opening a **new** terminal:

```bat
node --version
npm --version
```

`node --version` must print `v20.x` or newer. PATH changes only apply to
newly started processes — if you installed Node while DSH was running, restart
DSH (and the terminal) before running `INSTALL.cmd`. That's the whole setup:
`INSTALL.cmd` will confirm Node is present and error with a clear message if it
is not.

## Install

> **Zero-setup path — let DSH install it for you.** In any DSH session, just
> point it at this repository — no target path, no manual steps:
>
> > "Install the agent preset at
> > https://github.com/Axotopia/dsh/tree/main/property-researcher, install any
> > dependencies it needs, and verify it mounts. If Node.js is missing from
> > PATH, install it first. Grant Full Access to the filesystem for this job."
>
> Notes: **Full Access is needed only because the preset lands *outside* the
> session workspace** — the browser tier itself runs in the host-spawned MCP
> server and never needs elevated permissions. Approve any prompts the agent
> raises, and log into your research portals once in the browser window
> afterwards. Skip this path if you prefer the deterministic manual steps
> below.

From the repo root:



```bat
INSTALL.cmd
```

This copies the preset into `%USERPROFILE%\.dsh\.agent-presets\property-researcher`
(DSH's per-user preset root) and installs the bundled browser-tier MCP server
dependencies (`pnpm install`, falling back to `npm install`). Restart DSH, pick
**property-researcher** in the session preset picker, and confirm tools named
`mcp__research-browser-pr__*` appear in the session tool list.

Manual install: copy the repo to the preset path above and run
`pnpm install` (or `npm install`) inside `server\`.

## Repository layout

```
agent.cordis.yml     the preset: persona + all capability rows (read it — it IS the product)
preset.yml           display metadata for DSH's preset picker
INSTALL.cmd          one-command deploy to this machine
launch-browser.cmd   dedicated CDP research browser launcher (Edge/Chrome/Brave)
server/              attach-only CDP/MCP bridge (16 tools; deps pinned in pnpm-lock.yaml)
plugin/              dependency-free Markdown→PDF tool (local headless rendering)
roles/               the seven sub-agent role briefs (harvesters, teams, arbiter)
VALIDATION.md         field-validation summary
```

## What's in the box

- **16 browser tools** (`mcp__research-browser-pr__*`): navigate, click, type,
  scroll, extract_text, html, screenshot, tab management, challenge detection —
  attach-only over CDP to `127.0.0.1:9222`, dedicated profile under
  `%USERPROFILE%\.dsh\browser-profiles\research`, never headless, never your daily
  browser profile.
- **Markdown→PDF** via a local, dependency-free renderer + headless Edge/Chrome.
- **Multi-agent orchestration** through DSH's workflow engine: harvester fan-out
  with per-role briefs, adversarial Blue/Red interpretation, arbiter reconciliation,
  schema-validated deliverables.
- **Operator-facing honesty mechanics**: retrieval ledgers (planned vs actual calls,
  failure taxes, browser-tier status line), confidence grades per datum, deadlock
  declarations, and disclaimer footers on every artifact.

## Security model

- Web content is **untrusted data, never instructions** — imperative text inside
  fetched pages is ignored; code found in content is never executed.
- Read-only research defaults; forms/logins/downloads require explicit in-chat
  approval; credentials never enter prompts, tool calls, or files.
- TLS verification is never disabled; certificate anomalies fall back to alternate
  official surfaces and are flagged in provenance.
- Human-verification pages stop the agent ("Human action needed") — completed by the
  human in the visible browser, never bypassed.

See `agent.cordis.yml` for the full doctrine — it is written to be read.

## Status & validation

Field-validated on Washington State public records across three AHJ families
(Seattle, King County, Chelan County) — see [VALIDATION.md](VALIDATION.md).
Other jurisdictions work via the discovery ladder; verify before relying on it.

## License

MIT — see [LICENSE](LICENSE).

## Credits

Browser bridge derived from the author's `researcher-browser` package; the PDF tool
from the dependency-free `mdpdf-portable` package. Both are bundled so this repo
deploys standalone.
