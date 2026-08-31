# DeepSeek Harness Presets (DSH)

*A collection of experimental configurations and agentic workflows for DeepSeek Harness.*

## Overview
Welcome to the Axotopia **DSH** repository. This collection contains a set of presets, configurations, and multi-agent orchestration templates specifically designed to serve as a launchpad for your work with **DeepSeek Harness**. 

## The Architectural Approach to AI
We are rapidly moving past the era of standard prompt-and-response chatbots and into an architectural approach to artificial intelligence. Think of these presets not just as code, but as blueprints for cognitive workflows. Just as a physical building requires a solid foundation, load-bearing structures, and clear circulation paths, a multi-agent system needs structured routing, resilient memory management, and well-defined tools to operate reliably without collapsing under its own weight. These presets are designed with that structural integrity in mind.

## Steal it, or bring us in

**Self-serve: zero-setup.** The presets are MIT-licensed and free. No cloning, no `INSTALL.cmd`, no manual steps - in any DSH session, just point it at a preset folder in this repository and DSH installs it for you:

> "Install the agent preset at https://github.com/Axotopia/dsh/tree/main/researcher, install any dependencies it needs, and verify it mounts. Grant Full Access to the filesystem for this job."

Same pattern for every preset here - `researcher`, `property-researcher`, `research-swarm`, `debate-team`, `revit-tools`, `ocr-md`. Approve any prompts the agent raises (Full Access is needed only because the preset lands outside the session workspace). That self-serve path is genuinely enough for most research work.

**New: `research-swarm`** - a KIMI-style agent-swarm orchestrator fused with the high-agency research kit: parallel subagent fan-out with workflows and fresh-agent ralph rounds, an evidence-discipline research persona, and a real-browser CDP research tier that is queue-hardened so an entire swarm can safely share one dedicated browser. See [`research-swarm/README.md`](research-swarm/README.md).

**New: `ocr-md`** - verified local OCR to Markdown (and optional structured JSON) for images, PDFs, and whole folders: two independent passes - a dedicated OCR transcription model plus an exhaustive field-sweep pass - reconciled by a judge model that lists every disagreement, with raw-pass provenance files, a per-document conflict table, and phase-batched scheduling that amortizes local model loads on multi-page scans. The `researcher` preset integrates it: the agent never transcribes images itself and never trusts a single vision read - it runs the pipeline, then does the judgment work (consolidation, cross-page checks, numeric sanity) on the verified text. Runs entirely local via Ollama; the optional cloud tier is disabled unless three explicit opt-in conditions are met. See [`ocr-md/README.md`](ocr-md/README.md).

**Model note - vision is optional.** The browser tiers in `researcher`, `property-researcher`, and `research-swarm` do not require a vision-capable multimodal LLM: navigation, clicks by visible text, structured text extraction, tab management, and challenge detection (DOM-text signatures, not pixel analysis) are all text-based, and DSH substitutes a text placeholder for image content on routes declared text-only. The only vision-dependent tool is `screenshot` (PNG image content) - skip it on text-only models; vision-capable models can use it for layout checks, while measurements always come from page data, never pixels (evidence protocol). Document extraction does not depend on the session model at all: the `ocr-md` pipeline (integrated into `researcher`) turns images and PDFs into verified text on any model, so the extraction of record is always available.

**Bring us in.** For firms that need it customized - your jurisdictions, your data sources, your compliance rails, an audit panel built for your exact workflow - that's what Axoworks does. We're an architecture/engineering consultancy that ships these systems, not a vendor pushing a subscription. Tell us the research problem; we'll tell you whether a preset solves it or whether you need something bespoke.

> These presets are provided strictly as **proof of concept** models, not drop-in production solutions. Review the composition (`agent.cordis.yml`), routing, system prompts, and tool integrations, and adapt them to your data, hardware, and use cases.
## License
This project is open-source and available for public use under the **MIT License**. You are free to use, modify, and distribute this software as you see fit.

## Legal Disclaimer
**Disclaimer of Liability:**
The presets, scripts, and configurations provided in this repository are for educational, experimental, and proof-of-concept purposes only. They are provided "AS-IS" without warranties of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement.

In no event shall the authors, Axotopia, or copyright holders be liable for any claim, damages, or other liability, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the software or the use or other dealings in the software. Users are solely responsible for ensuring that their specific implementations comply with all applicable laws, data privacy regulations, and API terms of service.