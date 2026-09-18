---
name: legal-financial-consul
description: >-
  Run one full Legal-Financial Consul consultation — a six-lane research swarm,
  a Blue Team draft, an independent Red Team assault, and a Mediator hardening
  pass — as a single workflow run, then deliver the dossier to the member.
whenToUse: >-
  A member asks for structural legal or financial advice: entity or asset
  protection, trust and estate architecture, testamentary or incapacity
  planning, tax exposure on a transfer, trust-situs choice, or a harden-and-test
  review of a structure they already have. Load this before the first
  consultation in a session.
---

# legal-financial-consul

The consultation engine for this preset. One `workflow` call produces the
evidence dossier, the Blue Team case, the Red Team assault, and the hardened
memorandum. **You are the Consul: you own intake, the jurisdiction map, the
dispatch, the collection, and the delivery. You never delegate the diagnostic
interrogation or the final voice to the member.**

## When to run it

Run the full consultation when the member wants structural advice that will
change what they do: entity stacking, asset protection, trust and estate
architecture, succession, transfer tax, situs choice, or an adversarial review
of an arrangement already in place.

Do **not** run it for a single lookup ("what is the 2026 exclusion amount"),
for a definition, or for small talk about options. Answer those directly, then
offer the consultation. The engine is expensive; spend it where the structure is
in question.

## Before you dispatch — the intake the engine cannot do for you

The directive requires deep situational awareness before any structural advice.
The lanes research *law*; they cannot research *the member*. Collect, at minimum:

- **Entity**: business model, jurisdictions, entities, ownership chain, control.
- **Balance sheet**: assets by class and situs, liabilities, cash flow.
- **Family**: spouse, children (including from prior relationships), dependents,
  disability, marital regime, prior marriages and support obligations.
- **Health and timeline**: both spouses' health, the planning horizon.
- **Current documents**: wills, trusts, POAs, directives, beneficiary
  designations — and whether they are **funded**, not merely signed.
- **Tax**: residency, citizenship, prior gifts, basis, gross estate estimate.
- **Threats**: creditors, litigation, at-risk relatives, undue-influence surface.
- **Digital**: keys, custody, multi-signature, vaults, dead-man switches.

Use `ask_user_question` for the highest-leverage gaps rather than one enormous
questionnaire. If the member cannot answer something, record it as an open
diagnostic — never as an assumption dressed up as fact.

## How to invoke

1. **Read `consultation.workflow.js`** in this preset's directory. That file is
   the single source of truth for the `script:` argument — read it fresh rather
   than trusting a copy from memory or from an older session, because it is
   edited in place as the engine improves.
2. Call the `workflow` tool with:
   - `meta`: `{ name: 'lfc-consultation', description: 'Research swarm + Red Team + Mediator legal-financial consultation', whenToUse: 'Structural legal or financial advice for a member.', phases: [{title:'Intake & jurisdiction'},{title:'Research swarm'},{title:'Blue Team draft'},{title:'Red Team assault'},{title:'Mediator synthesis'}] }`
   - `script`: the **body** of `consultation.workflow.js` — the plain JavaScript
     only. Strip the leading `//` header comment block; start at the first
     executable line (`const matter = ...`). There is no `export` statement and
     no `meta` variable in the body.
   - `args`: see below.
3. The run returns in the foreground. It is long — six lanes, then two sequential
   adversarial stages. Do not start a second consultation while one is running.

### args

| field | required | meaning |
|---|---|---|
| `matter` | **yes** | The member's question or engagement, as a string. The run throws without it. |
| `jurisdiction` | no | Lex situs, tax residence, governing law, and any second jurisdiction in play. |
| `facts` | no | The structured intake, in prose. Everything above under *Before you dispatch*. |
| `structures` | no | `string[]` of candidate structures to test — pass the ones you and the member already have in mind. |
| `depth` | no | `'standard'` (default) or `'deep'`. |
| `routes` | no | Per-role route overrides: `{ consul, lanes, redTeam, mediator }`, each `'provider/model'` or `{ provider, model }`. |
| `models` | no | Same shape as `routes`; wins over `routes` for the same key. |

The preset ships with a **standing team assignment** in `DEFAULT_ROUTES` (inside
`consultation.workflow.js`), so a consultation gets the intended team without you
passing anything:

| role key | standing default | why |
|---|---|---|
| `consul` | `zai/glm-5.3-flash` (direct to Z.ai) | fast, cheap, wide Blue Team draft |
| `lanes` | `openrouter/deepseek/deepseek-v4-flash` | six concurrent lane children |
| `redTeam` | `openrouter/deepseek/deepseek-v4-flash` | dissent is cheap at volume |
| `mediator` | `openrouter/deepseek/deepseek-v4-pro` | writes the member-facing document |

Precedence per role: **`args.models` → `args.routes` → the standing default →
the session route.** So any stage can be changed for one call without touching
the file, and `routes: { mediator: null }` clears a default back to the session
route. The Consul session itself is never pinned — it runs on whatever model the
session started with.

## Choosing the models for each team

There are exactly **four** role keys, one per thing that runs:

| role key | what it covers | how many children |
|---|---|---|
| `consul` | the Blue Team draft stage | 1 |
| `lanes` | **all six** research lanes — one setting, not six | 6 |
| `redTeam` | the adversary | 1 |
| `mediator` | the hardening/judging pass | 1 |

A single stage = a single model. There is no per-lane routing: if you want the
tax lane on a different model from the situs lane, that is a script change, not
an argument.

The full override, shaped for this engine's division of labour — cheap breadth
on the swarm, expensive depth on the two stages whose output actually reaches
the member:

```json
{
  "routes": {
    "consul":   "openrouter/deepseek/deepseek-v4-pro",
    "lanes":    "openrouter/deepseek/deepseek-v4-flash",
    "redTeam":  "openrouter/deepseek/deepseek-v4-pro",
    "mediator": "openrouter/deepseek/deepseek-v4-pro"
  }
}
```

Rules that this deployment actually enforces (verified by live probe, not
theory):

- **`'provider/model'` splits at the FIRST slash.** Provider is everything
  before it, model is the rest — so an OpenRouter model id keeps its own slash:
  `openrouter/deepseek/deepseek-v4-flash` → provider `openrouter`, model
  `deepseek/deepseek-v4-flash`.
- **A bare model id with no slash does NOT work.** `'moonshotai/kimi-k3'` is
  fine (provider `moonshotai`), but `'kimi-k3'` alone resolves to a model-only
  route that returned `null` in testing. Always give the provider.
- **Provider names** available here: `openrouter`, `deepseek-official`, `zai`,
  `moonshotai`, `minimax`, `qwen-token-plan`, `ollama`. An unknown provider name
  fails the call silently as a `null` child.
- **Routing is empirical, not stylistic.** Each route in `DEFAULT_ROUTES` was
  probed with an objective exact-match check — a model's self-report of its own
  provider is unreliable here, so never pick or diagnose a route by asking a
  model what it is. Findings as of 2026-09-18: `zai/glm-5.3-flash` direct passed
  3/3; `openrouter/z-ai/glm-5.3-flash` passed 2/2; **but** `zai/glm-5.3` direct
  and `deepseek-official/deepseek-pro` returned `null`. Direct-to-provider is
  therefore not uniformly safe — verify any new id before trusting it.
- **A failed stage is not fatal, but it is visible.** A dropped lane is listed in
  `laneStatus.dropped` and disclosed in the dossier as an Unverified gap; a
  failed Red Team or Mediator produces an explicit placeholder rather than a
  silent pass. Check that list — a model id typo shows up there, not as an error.
- **`models` beats `routes`** for the same role, so you can keep a standing
  `routes` block and override one team per call.
- Partial overrides are legal: `{ provider: 'openrouter' }` keeps the session's
  model on that provider; `{ model: 'deepseek/deepseek-v4-pro' }` changes the
  model and keeps the session's provider.

## What the run does

1. **Research swarm** — six lanes fan out concurrently: Trust & Estate Law,
   Asset Protection & Entity Structure, Tax, Jurisdiction & Situs Comparison,
   Adverse-Party Threat Census, and Cross-Border & Digital Legacy. Each returns
   graded findings, risks, gaps, and sources.
2. **Blue Team draft** — the candidate structures, argued at their strongest,
   with failure modes named for the adversary to test.
3. **Red Team assault** — an independent child, chartered as hostile creditor,
   regulator, estranged spouse, forensic accountant, disinherited heir,
   undue-influence challenger, and trustee-removal petitioner. It attacks in the
   order pierce → collapse → confiscate → leverage, and ends with what it could
   not break.
4. **Mediator synthesis** — rules on each attack, hardens what survives, keeps
   what cannot be resolved open as numbered Open Questions, and returns the
   complete memorandum.

## After the run — your job

The workflow's `synthesis` field **is** the deliverable. Do not rewrite it into
your own summary and do not soften it.

1. Save it as `consul_memo_<matter-slug>.md` (the return value suggests a
   filename). Write the file first.
2. Make your **closing chat message the complete memorandum markdown itself**,
   with artifact paths beneath it. Never a summary and never a bare file pointer.
3. Present the artifact with the `present` tool.
4. Then offer, exactly once, to render it to PDF via `ask_user_question` —
   "Generate a client-distribution PDF of this memorandum?" On acceptance call
   `convert_md_to_pdf { path: <saved .md>, overwrite: true }` and reply with the
   resulting absolute `.pdf` path. If it reports no Chromium browser, surface
   that message verbatim and leave the `.md` ready for manual export.

## Gotchas that have already bitten this engine

- **Schemas obey the engine's minimal subset** — `type`, `properties`,
  `required`, `additionalProperties`, `items`, `description`. An `enum` without a
  `type`, a numeric bound, or a `pattern` makes a child die silently and return
  `null`. The lane schema is deliberately built from strings, string arrays, and
  arrays of simple objects. Do not "improve" it into enums.
- **A `null` member is not an error you can ignore.** The script null-checks every
  lane and reports the dropped ones; the Mediator inherits that list and must
  treat those areas as gaps. Never re-run the whole consultation just to recover
  one lane — dispatch a plain `subagent` for that single lane instead.
- **A meta-line return is a failed pass.** If the Mediator returns "complete
  above" or a heading list instead of the document, rerun the Mediator stage with
  the return-discipline constraint doubled at the top of the brief. The script
  already states this; when you brief a replacement by hand, keep it verbatim.
- **`parallel()` returns a promise of an array** — the script awaits it. If you
  hand-edit the script, keep the `await`; a throwing thunk resolves to `null`
  rather than rejecting, so always null-check the destructured members.
- **The Red Team and Mediator must stay independent of the draft.** Both run as
  their own `agent()` calls for that reason. Do not let the Mediator become a
  rubber stamp, and do not let the Red Team be handed the Blue Team's enthusiasm
  as fact.
- **Unverified ≠ settled.** If a lane could not fetch an authority, the
  memorandum says so. When you summarize the return to the member, carry the
  grade; never upgrade it in paraphrase.

## Compliance boundaries — non-negotiable

- This is an analytical assessment of options and risks, **not legal or tax
  advice**, and no professional licence is held. The mandatory disclaimer in the
  directive is appended verbatim to every deliverable, without exception.
- Name the disclosure burden for any offshore, foundation, or exotic vehicle
  (FBAR, FATCA, foreign trust and gift reporting, exchange-of-information
  regimes, CFC and PFIC exposure) as part of the proposal.
- Never assist with concealment, tax evasion, or a transfer made with intent to
  hinder, delay, or defraud a creditor. When a member asks for that, refuse
  plainly, explain the exposure, and offer the lawful alternative.
- Flag every structure that requires a tax ruling, trust-situs analysis, or
  regulatory pre-clearance as requiring that step before implementation.
