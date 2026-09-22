# Chat — a general-purpose DSH preset with an escalation ladder

**Agent preset for DeepSeek Harness (DSH).** A chat model first and an agent
second: most questions are answered with no tools at all, and heavier machinery
exists only for the questions that need it.

## What's in here

| Path | What |
|---|---|
| `agent.cordis.yml` | The composition — persona (which *is* the system prompt), the web tools, the delegation rows, compaction |
| `preset.yml` | Display name and description for the picker |
| `README.md` | This file |
| `LICENSE` | MIT |

No scripts, no bundled server, no skills, no dependencies. It is YAML and it runs
on the tooling DSH already installs.

## How it escalates

The design problem is not capability, it is restraint: every tool you mount is an
invitation to use it. So the persona names four rungs and forbids climbing one
just because it is available.

| Rung | When | Tools |
|---|---|---|
| **0 · ANSWER** | The default. Most questions need no tools at all. | none |
| **1 · CHECK** | The answer depends on current facts — news, prices, releases, versions, schedules, who holds a role. | `web_search`, `web_fetch` |
| **2 · RESEARCH** | The question is genuinely complex: several sources, a comparison, or conflicting claims to adjudicate. Still *you* working, not delegates. | `web_search`, `web_fetch`, used deliberately |
| **3 · SWARM** | Only when the work exceeds one context — many independent items, many documents, or a problem that needs repeated fresh-agent attack. | `subagent`, `list_agents`, `send_message`, `interrupt_agent`, `workflow`, `ralph` |

Eight tools in total. The rules that keep the ladder honest are in the persona:
a question answerable on rung 0 must be answered on rung 0; never search for
something you already know; never open with a plan or a promise to "look into
it"; when you delegate, write the brief as if the delegate knows nothing about
the conversation; and never hand the user raw delegate output.

Delegates join their parent's composition, so a spawned subagent inherits this
same persona — the persona therefore tells a delegate that it is one: do the
work, return findings, do not chat and do not re-delegate.

One rung-1 rule is worth repeating, because it is the most common way a web
answer goes wrong: `web_search` only *locates* sources — it returns titles and
URLs, not page text — so any claim that depends on what a page says must be read
with `web_fetch` first. The model is told never to answer from a headline, title
or URL, and to say in one line what it could not verify when a page will not
load or blocks it.

## Install

> **Zero-setup path — let DSH install it for you.** In any DSH session, point it
> at this repository:
>
> > "Install the agent preset at https://github.com/Axotopia/dsh/tree/main/chat,
> > install any dependencies it needs, and verify it mounts. Grant Full Access to
> > the filesystem for this job."
>
> Full Access is needed only because the preset lands *outside* the session
> workspace (`%USERPROFILE%\.dsh\.agent-presets\`). There is nothing to install:
> the web tools and the delegation rows resolve the host services DSH already
> mounts — the `subagents` registry and its spawn backend ship enabled in the
> base composition, with the delegation *tools* disabled until a preset enables
> them. This preset enables them.

Manual path — copy this folder into any preset root DSH scans:

- **Windows:** `%USERPROFILE%\.dsh\.agent-presets\chat`
- **macOS / Linux:** `~/.dsh/.agent-presets/chat`

```powershell
Copy-Item .\chat $env:USERPROFILE\.dsh\.agent-presets\chat -Recurse
```

Then pick **Chat** as the session mode in DSH.

## Use

Select the **Chat** preset and just talk to it. Simple questions get answered
from the model's own knowledge with no tool traffic; ask something that depends
on current facts and it checks the web; ask something genuinely hard and it may
run several searches, or — for work that will not fit in one context — fan out
to subagents, a workflow, or a ralph loop before answering.

Tuning knobs, if its judgement does not match yours:

| Want | Change |
|---|---|
| More or fewer searches per call | `searchMaxQueries` in the `tool-web` row (3 as shipped; the tool's own default is 4) |
| A shorter leash on ralph | `maxRounds` in the `tool-ralph` row (32 as shipped; the tool's default is 256) |
| Subsume the whole prompt | The persona is `complete: true`, so editing `persona.prefix` is editing the entire system prompt |
| The date in the prompt | `@deepseek-ai/dsh-time-context` is available and deliberately **not** mounted. It injects a timestamp message at *every* step through an `agent/pre-step` listener — a message injection, not a system-prompt section — so `includeRuntimeContext: false` does not suppress it. That is a per-turn cost, not a missing capability. Add the row (see the comment in `agent.cordis.yml`) if you would rather have the date on every turn |

## Design notes

- **`complete: true`, `includeRuntimeContext: false`.** The persona is the whole
  system prompt. This keeps it small, and — more importantly — means nothing
  except the persona steers the model: no generic tool guidance nudging it to
  delegate, and no sandbox/approval prose it has no use for, since this preset
  mounts no filesystem or shell tool. The delegation tools are still fully
  described by their own schemas; the persona says *when* to reach for them.
- **What is deliberately absent.** No filesystem, shell, jobs, todos, goals, plan
  mode, skills or `present`. None of them serve a chat turn, and each adds prompt
  guidance pulling toward multi-step behaviour.
- **It says out loud what it cannot do.** Because none of that is mounted, the
  persona states the limit plainly: no filesystem, shell, code execution or image
  reading, so it cannot open, save or edit a file, run a script, or read a
  document or image you attach. When a request needs that it says so in one line
  and offers the alternative that works — paste the relevant text, or point it at
  a URL. It never offers to save or export a file, and never pretends to have
  read something it had no way to read.
- **The delegation group mirrors the bundled `standard` preset's**, minus the two
  optional providers DSH does not install (codex, claude-code) and minus `fork`,
  whose in-process backend the host ships disabled. `workflowEngine` is isolated
  so the `workflow`/`ralph` tools and their worker share one engine of this
  preset's own — without that isolation a second preset publishing the same
  service would collide.
- **Compaction stays** (`compaction-basic` + the tool-result pruner). It adds no
  model-visible tool, and without it a long conversation dies on context instead
  of answering.
- **Derived from the shipped `standard` and `minimal` presets**, whose rows are
  MIT-licensed and ship with DSH.

## Sanitized for public distribution

This folder is a clean, self-contained copy:

- No credentials, API keys, or provider secrets — model routes live in your own
  settings.
- No machine paths, personal or company data, or account-specific endpoints.
- Neutral, generic personas and English metadata; no bundled examples tied to any
  specific project.

## License

MIT — see `LICENSE`.
