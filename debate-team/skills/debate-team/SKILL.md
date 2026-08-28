---
name: debate-team
description: >-
  Run a structured multi-LLM debate — 3 debaters (affirmative, negative, neutral
  expert) through opening, rebuttal rounds, and closing, then a moderator verdict —
  as a single workflow run.
whenToUse: >-
  The user asks for a debate, a debate team, a panel discussion, or a
  multi-perspective deliberation on a motion or topic.
---

# debate-team

A reusable multi-agent debate: **3 debaters + a moderator**, orchestrated by the
`workflow` tool. The moderator is the workflow script itself; it runs the rounds,
keeps context light, and ends with a structured verdict.

## When to use

- The user asks to debate a topic, wants a "debate team", a panel, or several
  independent model perspectives argued and then judged.
- Per the workflow-tool policy, use `workflow` **only** when the user explicitly
  asks for a debate / large multi-agent orchestration — do not launch one
  unprompted.

## How to invoke

1. Use the inline script at the bottom of this skill (or read the companion
   `debate-team.workflow.js` shipped with this folder).
2. Call the `workflow` tool with:
   - `meta` — `{ name: 'debate-team', description, whenToUse, phases }` (see below);
   - `script` — the script body verbatim (plain JS, ends with `return`);
   - `args` — the debate parameters (below).
3. The tool returns `{ motion, sides, openingStatements, rebuttalRounds,
   closingStatements, verdict, config }`. Surface the verdict to the user.

## args

| key | type | default | meaning |
|---|---|---|---|
| `motion` | string (required) | — | The debate motion/topic. |
| `context` | string | `''` | Optional background/facts all debaters should know. |
| `sides` | array | affirmative, negative, expert | Custom debaters: `[{ key, label, persona }]`, at least 2. |
| `models` | object | DEFAULT_ROUTES (null = inherit) | Per-role **route overrides** for this run: `{ affirmative, negative, expert, moderator }`. The standing team is set in `DEFAULT_ROUTES` inside the script. Each value is `{ provider, model }` or `"provider/model"`; `null` makes a role inherit the session route. |
| `rebuttalRounds` | number | `2` | Rebuttal rounds, `0`–`4`. |
| `maxWordsPerTurn` | number | `180` | Per-statement word cap, `60`–`600`. |

## meta phases

```js
{
  name: 'debate-team',
  description: 'Runs a structured debate among 3 debaters with a moderator verdict.',
  whenToUse: 'The user asks for a debate, debate team, panel, or multi-perspective deliberation.',
  phases: [
    { title: 'Opening statements', detail: 'Each debater states their opening position (parallel).' },
    { title: 'Rebuttal round 1', detail: 'Sequential turn-taking responses.' },
    { title: 'Rebuttal round 2', detail: 'Sequential turn-taking responses.' },
    { title: 'Closing statements', detail: 'Each debater gives a final position (parallel).' },
    { title: 'Moderator verdict', detail: 'The moderator scores each side and decides the outcome.' }
  ]
}
```

## Design rules (keep when adapting)

- **Strict personas.** Debaters never moderate, never summarize the whole debate,
  and never call tools. Enforced by the persona text; their permission scope is
  also fixed at delegation (approval pinned to `never`).
- **Context management.** Each debater gets a *condensed* state — the latest
  statements, truncated per side — never the raw transcript. The moderator
  verdict gets the full condensed transcript.
- **Structured output.** Debaters return `{ statement, keyPoints }`; the
  moderator returns `{ winner, summary, scores[], strongestArgument,
  weakestArgument }`. Schemas use only the engine-allowed keywords.
- **parallel vs sequential.** `parallel()` for independent turns (openings,
  closings); sequential awaits for turn-taking rebuttals so each debater sees the
  others' latest statements.
- **Plain JSON return.** No `undefined`, no functions — values cross a
  serialization boundary.

## Script

```js
// debate-team.workflow.js
// Multi-LLM debate: 3 debaters (affirmative, negative, neutral expert)
// argued through opening -> rebuttal rounds -> closing, then a structured
// moderator verdict. Runs as ONE `workflow` tool call.
//
// Invocation:
//   meta:   { name: 'debate-team', description, whenToUse, phases }  (see SKILL.md)
//   script: this file's body verbatim (plain JS, top-level await, ends with `return`)
//   args:   { motion, context?, sides?, models?, rebuttalRounds?, maxWordsPerTurn? }
//
// Design rules baked in:
//   - Debaters are strict role players: they never moderate, never summarize the
//     whole debate, and never call tools (their permission scope is fixed anyway).
//   - Context management: each debater receives a CONDENSED debate state, never
//     the raw transcript, so payloads stay light as rounds grow.
//   - Debaters return structured { statement, keyPoints }; the moderator returns
//     a structured verdict (winner, scores, strongest/weakest arguments).
//   - parallel() for independent turns (openings/closings), sequential awaits
//     for turn-taking (rebuttals, where each debater sees the others' latest).
//   - The returned value is plain JSON only (no undefined, no functions).

const motion = typeof args.motion === 'string' && args.motion.trim() ? args.motion.trim() : '';
if (!motion) throw new Error('args.motion is required: the debate motion/topic as a string.');

// ── configuration ────────────────────────────────────────────────────────────

const DEFAULT_SIDES = [
  {
    key: 'affirmative',
    label: 'Affirmative (Pro)',
    persona:
      'You are the Affirmative (Pro) debater. Your job is to argue FOR the motion as ' +
      'persuasively as possible: build a clear case, use logic and evidence, and defend it ' +
      'against counter-arguments. You are strictly a debater: do not moderate, do not ' +
      'summarize the whole debate, do not call any tools, and do not concede the motion.'
  },
  {
    key: 'negative',
    label: 'Negative (Con)',
    persona:
      'You are the Negative (Con) debater. Your job is to argue AGAINST the motion as ' +
      'persuasively as possible: expose its weaknesses, offer counter-examples and evidence, ' +
      'and attack the strongest pro arguments. You are strictly a debater: do not moderate, ' +
      'do not summarize the whole debate, do not call any tools, and do not concede the motion.'
  },
  {
    key: 'expert',
    label: 'Neutral Expert',
    persona:
      'You are the Neutral Expert. You take no side. Your job is to assess the arguments on ' +
      'both sides: flag factual errors, logical fallacies, unsupported claims, and evidence ' +
      'gaps, and point out the strongest and weakest arguments. Stay neutral and analytical. ' +
      'You are strictly an assessor: do not moderate, do not propose a winner, and do not call any tools.'
  }
];

// At least two custom sides are accepted: [{ key, label, persona }].
const sides = (Array.isArray(args.sides) && args.sides.length >= 2)
  ? args.sides.map((s, i) => ({
      key: String((s && s.key) || `side${i + 1}`),
      label: String((s && s.label) || `Debater ${i + 1}`),
      persona: String((s && s.persona) || 'You are a debater in this debate.')
    }))
  : DEFAULT_SIDES;

// Per-role route assignments: { affirmative, negative, expert, moderator }.
// DEFAULT_ROUTES is where you configure the team's models. Each value is
// "provider/model" (e.g. 'ollama/qwen2.5:14b' or 'deepseek/deepseek-chat'),
// { provider, model }, or null — null means "inherit the session route".
// A multi-LLM debate = different routes per role; leave all null for a
// same-model panel. args.models can override any single key at run time.
// Providers must have a registered adapter at call time.
const DEFAULT_ROUTES = {
  affirmative: null,   // PRO     — e.g. 'openrouter/deepseek-chat'
  negative: null,      // CON     — e.g. 'zai/glm-5.3'
  expert: null,        // NEUTRAL — e.g. 'moonshotai/kimi-k3'
  moderator: null      // MODERATOR — e.g. 'ollama/qwen2.5:32b'
};
const models = (args.models && typeof args.models === 'object' && !Array.isArray(args.models)) ? args.models : {};

// Normalize a route override ("provider/model" or { provider, model }) to
// AgentOptions-compatible { provider?, model? } fields.
function routeOverride(route) {
  const out = {};
  if (typeof route === 'string' && route) {
    const slash = route.indexOf('/');
    if (slash > 0) {
      out.provider = route.slice(0, slash);
      out.model = route.slice(slash + 1);
    } else {
      out.model = route;
    }
  } else if (route && typeof route === 'object') {
    if (typeof route.provider === 'string' && route.provider) out.provider = route.provider;
    if (typeof route.model === 'string' && route.model) out.model = route.model;
  }
  return out;
}

// Resolve the route for a role: args override wins, then the standing team default.
function routeFor(role) {
  return routeOverride(models[role] !== undefined ? models[role] : DEFAULT_ROUTES[role]);
}

const rebuttalRounds = Math.max(0, Math.min(4, Math.floor(Number(args.rebuttalRounds) || 2)));
const maxWords = Math.max(60, Math.min(600, Math.floor(Number(args.maxWordsPerTurn) || 180)));
const context = typeof args.context === 'string' ? args.context.trim() : '';

// ── helpers ──────────────────────────────────────────────────────────────────

function truncateWords(text, n) {
  const s = String(text || '').trim();
  const words = s.split(/\s+/).filter(Boolean);
  return words.length > n ? `${words.slice(0, n).join(' ')} …` : s;
}

function openingState() {
  return context ? `Background context: ${context}` : 'No prior statements — this is the opening of the debate.';
}

function roundState(label, turnLabel, roundIndex, others, own) {
  const lines = [`Round ${roundIndex} — ${turnLabel}. Latest statements:`];
  for (const o of others) lines.push(`— ${o.label}: ${truncateWords(o.statement, maxWords)}`);
  if (own) lines.push(`— Your own previous statement: ${truncateWords(own.statement, maxWords)}`);
  return lines.join('\n');
}

function fullTranscript(rounds) {
  const lines = ['Full condensed transcript:'];
  rounds.forEach((round, i) => {
    lines.push(`Round ${i + 1}:`);
    for (const r of round) lines.push(`— ${r.label}: ${truncateWords(r.statement, maxWords)}`);
  });
  return lines.join('\n');
}

// Structured per-debater output. Schema keywords limited to the engine contract:
// type/properties/required/additionalProperties/items/enum/const/oneOf.
const ARG_SCHEMA = {
  type: 'object',
  properties: {
    statement: { type: 'string' },
    keyPoints: { type: 'array', items: { type: 'string' } }
  },
  required: ['statement', 'keyPoints'],
  additionalProperties: false
};

async function runTurn(side, task, turnLabel, state, opts) {
  const prompt = [
    `${side.persona}`,
    '',
    `The motion under debate: "${motion}".`,
    context ? `Background context: ${context}` : '',
    '',
    'CURRENT DEBATE STATE (condensed):',
    state,
    '',
    `YOUR TASK THIS TURN — ${task}`,
    `Write at most ${maxWords} words. Stay in character as ${side.label}. Return the structured result.`
  ].filter(Boolean).join('\n');

  const result = await agent(prompt, {
    label: `${side.label} · ${turnLabel}`,
    phase: opts.phase,
    schema: ARG_SCHEMA,
    ...routeFor(side.key)
  });

  if (!result || typeof result !== 'object' || Array.isArray(result)) {
    return { side: side.key, label: side.label, statement: '[debater failed to respond]', keyPoints: [], failed: true };
  }
  return {
    side: side.key,
    label: side.label,
    statement: String(result.statement || ''),
    keyPoints: Array.isArray(result.keyPoints) ? result.keyPoints.map(String) : [],
    failed: false
  };
}

// ── debate flow ──────────────────────────────────────────────────────────────

phase('Opening statements');
const openings = await parallel(sides.map((side) => () =>
  runTurn(
    side,
    'Opening statement: state your position and your strongest arguments.',
    'opening',
    openingState(),
    { phase: 'Opening statements' }
  )
));
log(`Openings complete for ${sides.length} debaters.`);

const rebuttals = [];
for (let r = 1; r <= rebuttalRounds; r++) {
  const phaseTitle = `Rebuttal round ${r}`;
  phase(phaseTitle);
  const previous = r === 1 ? openings : rebuttals[r - 2];
  const roundResults = [];
  for (const side of sides) {
    const others = previous.filter((p) => p.side !== side.key);
    const own = previous.find((p) => p.side === side.key);
    const state = roundState(side.label, 'rebuttal', r, others, own);
    const res = await runTurn(
      side,
      `Rebuttal: respond to the other debaters' latest statements above. Defend your own position, attack their weakest claims, and advance your case.`,
      'rebuttal',
      state,
      { phase: phaseTitle }
    );
    roundResults.push(res);
    log(`${side.label}: rebuttal ${r} recorded.`);
  }
  rebuttals.push(roundResults);
}

phase('Closing statements');
const transcript = [openings, ...rebuttals];
const closings = await parallel(sides.map((side) => () =>
  runTurn(
    side,
    'Closing statement: state your final position for this debate, incorporating the exchanges so far.',
    'closing',
    fullTranscript(transcript),
    { phase: 'Closing statements' }
  )
));

phase('Moderator verdict');
const verdictPrompt = [
  'You are the debate moderator and judge. You have just run a structured debate.',
  '',
  `The motion was: "${motion}".`,
  context ? `Background context: ${context}` : '',
  '',
  'Below is the condensed transcript of the debate among:',
  ...sides.map((s) => `- ${s.label}`),
  '',
  fullTranscript([...transcript, closings]),
  '',
  'Now judge the debate fairly and on the merits:',
  '- summarize how each side performed;',
  '- score each side;',
  '- name the winner, or declare a split decision;',
  '- identify the single strongest and the single weakest argument made.',
  'Return the structured verdict.'
].filter(Boolean).join('\n');

const verdictRaw = await agent(verdictPrompt, {
  label: 'Moderator · verdict',
  phase: 'Moderator verdict',
  schema: {
    type: 'object',
    properties: {
      winner: { type: 'string' },
      summary: { type: 'string' },
      scores: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            side: { type: 'string' },
            score: { type: 'number' },
            rationale: { type: 'string' }
          },
          required: ['side', 'score', 'rationale'],
          additionalProperties: false
        }
      },
      strongestArgument: { type: 'string' },
      weakestArgument: { type: 'string' }
    },
    required: ['winner', 'summary', 'scores', 'strongestArgument', 'weakestArgument'],
    additionalProperties: false
  },
  ...routeFor('moderator')
});

const verdict = (verdictRaw && typeof verdictRaw === 'object' && !Array.isArray(verdictRaw))
  ? {
      winner: String(verdictRaw.winner || 'undetermined'),
      summary: String(verdictRaw.summary || ''),
      scores: Array.isArray(verdictRaw.scores)
        ? verdictRaw.scores
            .filter((s) => s && typeof s === 'object')
            .map((s) => ({
              side: String(s.side || ''),
              score: Number(s.score) || 0,
              rationale: String(s.rationale || '')
            }))
        : [],
      strongestArgument: String(verdictRaw.strongestArgument || ''),
      weakestArgument: String(verdictRaw.weakestArgument || '')
    }
  : {
      winner: 'undetermined',
      summary: 'The moderator could not produce a verdict (agent failure).',
      scores: [],
      strongestArgument: '',
      weakestArgument: ''
    };

log('Debate complete.');

return {
  motion,
  sides: sides.map((s) => ({ key: s.key, label: s.label })),
  openingStatements: openings,
  rebuttalRounds: rebuttals,
  closingStatements: closings,
  verdict,
  config: { rebuttalRounds, maxWordsPerTurn: maxWords }
};
```
