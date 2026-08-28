# Debate Team — a DSH agent preset for structured multi-LLM debates

A [DeepSeek Harness](http://127.0.0.1) **agent preset** that turns a session into a
**debate operator**: when you ask for a debate or a multi-perspective verdict, it
runs one structured `workflow` debate — **Affirmative (Pro)** vs **Negative (Con)**
with a **Neutral Expert** fact-checking both — then a **Moderator** renders a
structured verdict (winner, per-side scores, strongest/weakest argument).

This is the *session mode* companion to the **debate-team** script + skill. If you
just want the runnable thing without a new session mode, grab that instead — see
the sibling `debate-team-public` package for the standalone script, skill, and README.

## What's in here

| File | Purpose |
|---|---|
| `agent.cordis.yml` | The preset composition — a copy of the shipped `standard` toolset (shell, filesystem, skills, goals, plan, compaction, delegation + workflow) with the persona swapped to a **debate operator**. |
| `preset.yml` | Metadata (name / description / order) shown by the roster & settings UI. |
| `skills/debate-team/SKILL.md` | The bundled debate skill (self-contained — includes the orchestration script) so a session on this preset can run a debate on request. Bundling it under `skills/` is what makes it auto-discoverable for this preset. |
| `debate-team.workflow.js` | The orchestration script (canonical copy) — the skill embeds the same body. |
| `LICENSE` | MIT. |

## Install

> **Zero-setup path — let DSH install it for you.** In any DSH session, just
> point it at this repository — no target path, no manual steps:
>
> > "Install the agent preset at
> > https://github.com/Axotopia/dsh/tree/main/debate-team, and verify it
> > mounts — start a session on the Debate Team mode and ask for a short
> > test debate. Grant Full Access to the filesystem for this job."
>
> Notes: **Full Access is needed only because the preset lands *outside* the
> session workspace** (%USERPROFILE%\.dsh\.agent-presets\) — the debate
> itself runs as workflow children under fixed, non-escalating scope and never
> needs elevated permissions. There are no dependencies to install: the panel
> is YAML + one skill + one script, and all model traffic goes through your
> existing DSH provider configuration. Approve any prompts the agent raises,
> and add missing provider keys in Settings → Models if the test debate
> reports a failed seat. Skip this path if you prefer the deterministic manual
> steps below.

A preset is a directory holding an `agent.cordis.yml`. Copy this folder (renamed
`debate-team`) into any preset root DSH scans. The user root is per-machine:

- **Windows:** `%USERPROFILE%\.dsh\.agent-presets\debate-team`
- **macOS / Linux:** `~/.dsh/.agent-presets/debate-team`

Or drop it under a project-scoped preset root (whatever your deployment configures).

```powershell
# user root (Windows)
New-Item -ItemType Directory -Force $env:USERPROFILE\.dsh\.agent-presets | Out-Null
Copy-Item .\debate-team-preset-public $env:USERPROFILE\.dsh\.agent-presets\debate-team -Recurse
```

Then in DSH, pick the **Debate Team** mode for a session.

## Use

1. Select the **Debate Team** preset as your session mode.
2. Ask for a debate — e.g. **"Debate: this house believes open source should dominate enterprise AI."**
3. The operator runs one `workflow` call (openings → rebuttal rounds → closing → moderatory verdict) and surfaces the verdict + transcript.

> The `workflow` tool is used only when you ask for a debate / large multi-agent
> orchestration (per its policy). For an ordinary question the operator just does
> the task — it does not launch a debate unprompted.

## Configure the models (make it a real multi-LLM panel)

The script doesn't care which models you use. Open `debate-team.workflow.js` and set
`DEFAULT_ROUTES` — this is where the standing team lives:

```js
const DEFAULT_ROUTES = {
  affirmative: 'openrouter/deepseek-chat',          // PRO
  negative:    { provider: 'zai', model: 'glm-5.3' }, // CON
  expert:      'moonshotai/kimi-k3',                // NEUTRAL
  moderator:   'ollama/qwen2.5:32b'                 // REFEREE
};
```

Each value is `"provider/model"`, `{ provider, model }`, or `null` (inherit the
session route). All-`null` is a valid same-model panel. Providers must have a
registered adapter in your DSH settings at call time.

## Why the persona matters

The composition is deliberately the full `standard` toolset with a narrower persona.
That matters for two reasons:

- **The preset isn't the debaters.** A preset composes *one* agent. The debaters are
  subagents spawned at call time by the `workflow` engine; the moderator is the
  script. You cannot configure three different debater plugins or assign models in
  a preset — that's a common misconception. The workflow engine is the orchestration
  seam.
- **Strict roles.** The operator's persona enforces the important rule: the debaters
  argue, the expert fact-checks, the moderator judges — nobody summarizes the whole
  debate or calls tools, and the operator never argues for a side.

## Sanitized for public distribution

This folder is a clean, self-contained copy:
- No credentials, API keys, or provider secrets (model routes live in your own settings).
- No machine paths, personal or company data, or account-specific endpoints.
- Neutral, generic personas and English metadata; no bundled examples tied to any specific project.

## License

MIT — see `LICENSE`.
