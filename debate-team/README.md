# debate-team — a multi-LLM debate panel for DeepSeek Harness

A reusable **3-debater + moderator** debate engine that runs inside [DeepSeek Harness (DSH)](http://127.0.0.1) as a single `workflow` tool run. Three role-bounded models argue a motion across opening statements, rebuttal rounds, and closings — then a moderator judge produces a structured verdict with scores, the strongest and weakest arguments, and a winner.

```
Opening statements (parallel)
   ├─ PRO    — argues FOR the motion
   ├─ CON    — argues AGAINST the motion
   └─ NEUTRAL — expert assessor: flags fallacies, evidence gaps, weak claims
Rebuttal round 1 (sequential turn-taking, each sees the others' latest)
Rebuttal round 2 (sequential turn-taking)
Closing statements (parallel)
Moderator verdict (structured: winner, scores, strongest/weakest arguments)
```

Each role runs on **its own model route** — point PRO, CON, NEUTRAL, and MODERATOR at different providers/models for a genuine multi-LLM panel, or leave them all on your session model.

## What this is (and isn't)

| Piece | Role |
|---|---|
| `debate-team.workflow.js` | The orchestration script (the "moderator's engine"). Runs inside the `workflow` tool: phases, parallel/sequential turns, per-role model routes, structured-output schemas. |
| `skills/debate-team/SKILL.md` | A DSH skill — self-contained (inline script included) — so any session can load the playbook and run a debate on user request. |
| Your DSH install | Provides the actual primitives: the `workflow` tool, subagent children, and your configured model providers. Nothing here talks to APIs directly. |

It is **not** a new agent type, plugin, or preset — it is configuration + one orchestration script on top of DSH's existing multi-agent primitives. You can't "hack the core" to do this; the workflow engine is the designed seam.

## Requirements

- DeepSeek Harness Desktop (developed and tested on `0.1.1-rc.2`; you need a build that ships the `workflow` tool — the shipped `standard` preset already grants it).
- At least one configured model provider. For a true multi-LLM panel, configure two or three providers and make sure their API keys are set in DSH settings.
- Local models (e.g. Ollama) work for any role, provided the server is running and the model is pulled.

## Install

Pick whichever fits your workflow:

**Option A — as a skill (recommended).** Copy the skill bundle into a skill root. DSH scans, in priority order:

1. `<project>/.dsh/skills` — per-repo
2. `~/.dsh/skills` (`%USERPROFILE%\.dsh\skills` on Windows) — per-user, all projects

```powershell
# project-level
New-Item -ItemType Directory -Force .\.dsh\skills\debate-team | Out-Null
Copy-Item skills\debate-team\SKILL.md .\.dsh\skills\debate-team\SKILL.md

# or user-level
New-Item -ItemType Directory -Force $env:USERPROFILE\.dsh\skills\debate-team | Out-Null
Copy-Item skills\debate-team\SKILL.md $env:USERPROFILE\.dsh\skills\debate-team\SKILL.md
```

Also drop `debate-team.workflow.js` somewhere your project keeps scripts (optional — the skill is self-contained).

**Option B — script only.** Keep `debate-team.workflow.js` in your workspace and ask your agent to run it with the `workflow` tool (it must pass `meta` + `script` + `args`; see below).

## Configure your team

Open `debate-team.workflow.js` and set `DEFAULT_ROUTES` — the single place where roles meet models:

```js
const DEFAULT_ROUTES = {
  affirmative: 'openrouter/deepseek-chat', // PRO     — "provider/model" string
  negative:    { provider: 'zai', model: 'glm-5.3' }, // CON — or an object
  expert:      'moonshotai/kimi-k3',      // NEUTRAL
  moderator:   'ollama/qwen2.5:32b'       // MODERATOR — local model works too
};
```

Each value is `"provider/model"`, `{ provider, model }`, or `null`. `null` means *inherit the session route* — all-null is a valid (same-model) panel. Providers must have a registered adapter in your DSH settings at call time.

**Prefer lineage diversity, not just vendor diversity.** Models from one lineage share a routing layer and an invisible baseline (see *Three Ways an AI Lies to You*, axoworks.com/articles/three-ways-ai-lies); a panel drawn from a single culture can amplify a blind spot instead of checking it. Put the contrast on the adversarial axis — PRO vs CON — and draw NEUTRAL and MODERATOR from yet other lineages.

## Usage

With the skill installed, just ask:

> **You:** Debate: *this house believes open source should dominate enterprise AI*
> **Agent:** (runs one `workflow` call → returns the full structured transcript + verdict)

Direct invocation arguments (the `args` object of the `workflow` tool call):

| key | type | default | meaning |
|---|---|---|---|
| `motion` | string (required) | — | The debate motion/topic. |
| `context` | string | `''` | Optional background/facts all debaters receive. |
| `sides` | array | PRO / CON / NEUTRAL | Custom debaters: `[{ key, label, persona }]`, at least 2 roles. |
| `models` | object | `DEFAULT_ROUTES` | Per-run route overrides, any of `{ affirmative, negative, expert, moderator }`. |
| `rebuttalRounds` | number | `2` | Rebuttal rounds, `0`–`4`. |
| `maxWordsPerTurn` | number | `180` | Per-statement word cap, `60`–`600`. |

A minimal call:

```js
args = { motion: 'AI coding agents will replace most human developers within 10 years' }
```

## What you get back

Plain JSON — one object with the full debate:

```json
{
  "motion": "…",
  "sides": [{ "key": "affirmative", "label": "Affirmative (Pro)" }, "…"],
  "openingStatements": [
    { "side": "affirmative", "statement": "…", "keyPoints": ["…"], "failed": false }
  ],
  "rebuttalRounds": [ [ "… per round, per side …" ] ],
  "closingStatements": [ "…" ],
  "verdict": {
    "winner": "Negative (Con)",
    "summary": "…",
    "scores": [{ "side": "…", "score": 7, "rationale": "…" }],
    "strongestArgument": "…",
    "weakestArgument": "…"
  },
  "config": { "rebuttalRounds": 2, "maxWordsPerTurn": 180 }
}
```

## Design principles (keep these when adapting)

- **Strict role personas.** Debaters never moderate, never summarize the whole debate, and never call tools. (Their sandbox/approval scope is also fixed at delegation time, so they can't self-escalate.)
- **Context management.** Every debater gets a *condensed* debate state — the previous round's statements, truncated per role — never the raw transcript. The moderator gets the full condensed transcript. This keeps payloads bounded as rounds grow.
- **Structured output.** Debaters return `{ statement, keyPoints }`; the moderator returns a verdict object. Schemas are limited to the workflow engine's allowed keyword set.
- **Parallel vs sequential.** Independent turns (openings, closings) run in parallel; rebuttal rounds run sequentially so each debater reacts to the others' latest statements.
- **Graceful degradation.** A child that fails (bad route, missing key, provider error) returns a clearly marked `[debater failed to respond]` placeholder; the debate and the verdict still complete, and the moderator will note the absence.

## Troubleshooting

- **A debater returns `[debater failed to respond]`** → the route didn't resolve: provider id unknown to DSH, missing/invalid API key, model id not served by that provider, or Ollama not running. Fix the route in `DEFAULT_ROUTES` or `args.models`.
- **Probe a route before a long debate** (quick workflow one-liner): run `workflow` with a script that does `return agent('Reply OK', { label: 'probe', provider: '…', model: '…' })` — a non-null result means the route works.
- **`args.motion is required`** → pass the motion as a non-empty string.
- **Debate feels shallow** → raise `rebuttalRounds` (up to 4) or `maxWordsPerTurn` (up to 600), or give richer `context`.

## Cost & safety notes

- Each statement is a real model call: a default debate is **13 calls** (3 openings + 6 rebuttals + 3 closings + 1 verdict), each with its own context. Route your most expensive model to the role that benefits (usually the moderator).
- All model traffic goes through your existing DSH provider configuration — there are no new endpoints, keys, or credentials in this repo.
- Debate children inherit the standard DSH sandbox; they cannot widen their own permissions.

## License

MIT — see [LICENSE](LICENSE). (Add your name/copyright line before publishing.)
