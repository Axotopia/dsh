# DeepSeek Harness Presets (DSH)

*A collection of experimental configurations and agentic workflows for DeepSeek Harness.*

## Overview
Welcome to the Axotopia **DSH** repository. This collection contains a set of presets, configurations, and multi-agent orchestration templates specifically designed to serve as a launchpad for your work with **DeepSeek Harness**. 

## What is DeepSeek Harness?
**DeepSeek Harness (DSH)** is the open-source agent runtime every preset in this repository runs on. It pairs a local-first agent loop (persistent sessions with shell, filesystem, and browser tools, subagents, workflow orchestration, jobs, and skills) with a **Cordis plugin composition system**: every capability is a plugin row in a `cordis.yml`, and an **agent preset** is one such composition file mounted for a single session - which is exactly what the folders in this repo are.

- **Desktop app (Windows/macOS, free):** [anywhere-labs/dsh-desktop](https://github.com/anywhere-labs/dsh-desktop) - a community-maintained open-source project (not an official DeepSeek product) that bundles the harness with a web UI at `http://127.0.0.1:43120`.
- **Your presets live in** `~/.dsh/.agent-presets/<preset-id>/` - each a directory holding an `agent.cordis.yml` composition plus a `preset.yml` manifest; the desktop app discovers them automatically and offers them as new-session presets.
- **Zero-setup install:** see the self-serve prompt below - point a DSH session at a preset folder here and it installs, mounts, and verifies the preset for you.

## The Architectural Approach to AI
We are rapidly moving past the era of standard prompt-and-response chatbots and into an architectural approach to artificial intelligence. Think of these presets not just as code, but as blueprints for cognitive workflows. Just as a physical building requires a solid foundation, load-bearing structures, and clear circulation paths, a multi-agent system needs structured routing, resilient memory management, and well-defined tools to operate reliably without collapsing under its own weight. These presets are designed with that structural integrity in mind.

## Steal it, or bring us in

**Self-serve: zero-setup.** The presets are MIT-licensed and free. No cloning, no `INSTALL.cmd`, no manual steps - in any DSH session, just point it at a preset folder in this repository and DSH installs it for you:

> "Install the agent preset at https://github.com/Axotopia/dsh/tree/main/researcher, install any dependencies it needs, and verify it mounts. Grant Full Access to the filesystem for this job."

Same pattern for every preset here - `chat`, `researcher`, `property-researcher`, `research-swarm`, `debate-team`, `legal-financial-consul`, `revit-tools`, `ocr-md`, `vacation-planner`. Approve any prompts the agent raises (Full Access is needed only because the preset lands outside the session workspace). That self-serve path is genuinely enough for most research work.

**New: `chat`** - a general-purpose assistant with an escalation ladder, in the shape of the chat models you already use. It answers from its own knowledge by default and mounts no filesystem or shell tool at all; it checks the web when the answer depends on current facts; it runs a deliberate multi-source research pass when a question is genuinely complex; and it fans out to subagents, a workflow or a ralph loop only when the work exceeds one context. The whole design problem is restraint, so the persona names the four rungs explicitly and forbids climbing one because it is available - a question answerable without tools must be answered without tools. Eight tools in total. See [`chat/README.md`](chat/README.md).

**New: `legal-financial-consul`** - a fiduciary-grade legal and financial Consul: it interrogates the fact pattern, fans a six-lane research swarm across primary authority (trust and estate law, asset protection, tax, situs comparison, an adverse-party threat census, and cross-border/digital legacy), then puts every candidate structure through an independent Red Team assault and a Mediator hardening pass before delivering a graded, cited memorandum with the four mortality scenarios and a residual-risk register. It is not legal advice and says so in writing. See [`legal-financial-consul/README.md`](legal-financial-consul/README.md).

**New: `research-swarm`** - a KIMI-style agent-swarm orchestrator fused with the high-agency research kit: parallel subagent fan-out with workflows and fresh-agent ralph rounds, an evidence-discipline research persona, and a real-browser CDP research tier that is queue-hardened so an entire swarm can safely share one dedicated browser. See [`research-swarm/README.md`](research-swarm/README.md).

**New: `ocr-md`** - verified local OCR to Markdown (and optional structured JSON) for images, PDFs, and whole folders: two independent passes - a dedicated OCR transcription model plus an exhaustive field-sweep pass - reconciled by a judge model that lists every disagreement, with raw-pass provenance files, a per-document conflict table, and phase-batched scheduling that amortizes local model loads on multi-page scans. Three presets integrate it - `researcher`, `research-swarm`, and `property-researcher`: the agent never transcribes images itself and never trusts a single vision read - it runs the pipeline, then does the judgment work (consolidation, cross-page checks, numeric sanity) on the verified text. Runs entirely local via Ollama; the optional cloud tier is disabled unless three explicit opt-in conditions are met. See [`ocr-md/README.md`](ocr-md/README.md).

**New: `vacation-planner`** - a gourmet travel planner for serious foodies: anchor meals first with Eater/Michelin/local-critic sourcing (Yelp and TripAdvisor demoted to logistics-only, never taste evidence), event and museum-calendar alignment before any dinner is fixed, reservation-platform mechanics and drop times, flight/train booking horizons, and a day-by-day itinerary file with a deadline-ordered booking checklist and date-stamped verification log. Luxury dining to camping/glamping. See [`vacation-planner/README.md`](vacation-planner/README.md).

**New: `statement-consolidator`** - a bookkeeper for year-end reporting: ingests bank and credit-card statements (CSV / XLSX) from any institution and any layout, normalizes them to one canonical JSON schema, and learns + persists the per-institution field mapping (confirmed once, reused forever); then consolidates the year's statements from many institutions into one big master file (canonical JSON + CSV) plus a multi-sheet Excel workbook (all transactions, account summaries, reconciliation, continuity, duplicates, coverage gaps, exceptions, and the mappings-used audit). A deterministic reconciliation gate must PASS (`opening + Σ transactions == closing`), with duplicate / double-import detection, cross-statement continuity, month-coverage gaps, and a full audit trail. Model-free, stdlib-only, no network, and no number is ever invented — unmapped raw columns go to `extras` verbatim. See [`statement-consolidator/README.md`](statement-consolidator/README.md).

**Model note - vision is optional.** The browser tiers in `researcher`, `property-researcher`, and `research-swarm` do not require a vision-capable multimodal LLM: navigation, clicks by visible text, structured text extraction, tab management, and challenge detection (DOM-text signatures, not pixel analysis) are all text-based, and DSH substitutes a text placeholder for image content on routes declared text-only. The only vision-dependent tool is `screenshot` (PNG image content) - skip it on text-only models; vision-capable models can use it for layout checks, while measurements always come from page data, never pixels (evidence protocol). Document extraction does not depend on the session model at all: the `ocr-md` pipeline (integrated into `researcher`, `research-swarm`, and `property-researcher`) turns images and PDFs into verified text on any model, so the extraction of record is always available.

**Bring us in.** For firms that need it customized - your jurisdictions, your data sources, your compliance rails, an audit panel built for your exact workflow - that's what Axoworks does. We're an architecture/engineering consultancy that ships these systems, not a vendor pushing a subscription. Tell us the research problem; we'll tell you whether a preset solves it or whether you need something bespoke.

> These presets are provided strictly as **proof of concept** models, not drop-in production solutions. Review the composition (`agent.cordis.yml`), routing, system prompts, and tool integrations, and adapt them to your data, hardware, and use cases.
## Changelog

### 2026-09-21 — add the `chat` preset

A general-purpose assistant that behaves like a chat model first and an agent
second, with escalation made explicit rather than left to the model's judgement.
Four rungs — answer, check, research, swarm — and a persona that forbids climbing
one because it is available. Eight tools: `web_search`, `web_fetch`, `subagent`,
`list_agents`, `send_message`, `interrupt_agent`, `workflow`, `ralph`.

Two things are deliberate about the composition. The persona is
`complete: true` with `includeRuntimeContext: false`, so *nothing but the persona*
steers the model — no generic tool guidance nudging it to delegate, and no
sandbox/approval prose, since the preset mounts no filesystem or shell tool. And
it mounts none of the usual scaffolding: no filesystem, shell, jobs, todos,
goals, plan mode or skills, because none of them serve a chat turn.

The delegation group mirrors the bundled `standard` preset's, minus the two
optional providers DSH does not install (codex, claude-code) and minus `fork`,
whose in-process backend the host ships disabled. `workflowEngine` is isolated so
`workflow`/`ralph` and their worker share one engine of the preset's own.

### 2026-09-21 — the browser tier now starts off Windows

The browser presets were Windows-first: their MCP rows derived the server's
working directory from `process.env.USERPROFILE`, which is unset on Linux and
macOS. `dsh-mcp-client` passes that `cwd` straight to `spawn`, so the server
could not start and the client **dropped it silently** — the preset composed and
looked healthy, but its `mcp__*__*` browser tools were simply absent, with no
error raised anywhere.

- **MCP `cwd`** in `researcher`, `research-swarm`, `medical-technician` and
  `property-researcher` now resolves
  `(process.env.USERPROFILE || process.env.HOME)`, which is correct on every
  platform.
- **`legal-financial-consul`** used `cwd: ./server`. Node resolves a relative
  `cwd` against the *process* working directory, not the preset folder, so that
  server could not start either; it now uses the same home-derived path.
- **`revit-tools`** carried a hardcoded `C:\Users\desig\...` path — a per-machine
  placeholder. It is now home-derived. The preset still requires Autodesk Revit.
- **`launch-browser.sh`** now ships beside `launch-browser.cmd` in all five
  browser-tier presets, and `server/server.js` selects the launcher by platform.
  Windows behaviour is unchanged: it still goes through `cmd.exe` with
  `launch-browser.cmd`. The "run the launcher yourself" message names the right
  file for the platform.
- **`ocr-md-json`** now names both platforms' script locations and the correct
  interpreter (`python3` on Linux/macOS, `py` on Windows).

Verified with a row-config validator that runs every row's `config` through the
`Config` schema its own plugin exports, interpolating `!!js` exactly as the
Loader does: every row config in every preset validates. Preset *discovery*
cannot catch this class of defect — it validates YAML shape and module
resolution, never `config` — which is why a silently-absent MCP server still
reads as a healthy preset.

Still Windows-only, unchanged: the `ocr-md` PowerShell pipeline (`ocr.ps1`) and
`revit-tools`' Revit executable. Persona prose in the browser presets still names
`%USERPROFILE%` in its launcher fallback; automatic launch makes that path rarely
reached, and it was left as written to keep this diff reviewable.

## License
This project is open-source and available for public use under the **MIT License**. You are free to use, modify, and distribute this software as you see fit.

## Legal Disclaimer
**Disclaimer of Liability:**
The presets, scripts, and configurations provided in this repository are for educational, experimental, and proof-of-concept purposes only. They are provided "AS-IS" without warranties of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement.

In no event shall the authors, Axotopia, or copyright holders be liable for any claim, damages, or other liability, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the software or the use or other dealings in the software. Users are solely responsible for ensuring that their specific implementations comply with all applicable laws, data privacy regulations, and API terms of service.