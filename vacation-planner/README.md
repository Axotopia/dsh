# Vacation Planner — a DSH agent preset for gourmet travel planning

A [DeepSeek Harness](http://127.0.0.1) **agent preset** that turns a session into a
**food-first travel planner** for serious foodies: people who book trips around
tasting menus and new openings, care about museums, markets, and what is actually
on in town, and are equally happy at a two-star counter or a well-sited campsite.
It researches where to stay, eat, drink, and visit; aligns the plan with local
events; works out the flights, trains, and transfers; and delivers a day-by-day
itinerary file with a booking checklist — notes to act on, not narrative prose.

## What's in here

| File | Purpose |
|---|---|
| `agent.cordis.yml` | The preset composition — the full shipped `standard` toolset (shell, filesystem, web search + fetch, skills, goals, plan mode, compaction, delegation + workflow, jobs) with the persona swapped to a **gourmet travel planner**, plan mode re-aimed at itinerary planning, and a clock context row for reservation-window math. |
| `preset.yml` | Metadata (name / description) shown by the roster & settings UI. |
| `skills/gourmet-travel-method/SKILL.md` | The bundled method skill — the planner's operating manual (below). Bundling it under `skills/` is what makes it auto-discoverable for this preset. |
| `LICENSE` | MIT. |

## How it plans

The `gourmet-travel-method` skill carries the method. The highlights:

**Taste-source hierarchy.** Editorial sources judge taste; crowd aggregates never
do. Promoted: **Eater** (Eater 38 / Heatmap for "new and hot"), **Michelin**
(Stars, Bib Gourmand, Keys), local critics and city media, World's 50 Best /
La Liste as of-the-moment radar, NYT / Bon Appétit / Food & Wine. **Demoted to
logistics-only:** Yelp, TripAdvisor, and Google review scores — hours, phones,
complaint scans; never rankings. Every taste claim names its source.

**Reservation mechanics.** A per-city platform map (Resy Notify, Tock's ~9–10 a.m.
cancellation window, SevenRooms, OpenTable, Japan's Pocket Concierge / OMAKASE /
TableCheck), drop-time skepticism (never plan around a forum-posted drop time —
confirm by phone), the escalation ladder (alert → weekday-morning call → concierge
→ card dining programs → paid secondary), and the value moves (bar/counter seats,
lunch at the same kitchen, Bib Gourmand filling).

**Events first.** Tourism-board calendars, Time Out, museum exhibition pages with
timed-entry booking, festival and market-day calendars, closure days — all on one
timeline **before** any dinner is fixed, because events dictate which neighborhood
the traveler occupies at which hour.

**Transit that respects the table.** Google Flights / ITA Matrix / Skyscanner for
air; The Man in Seat 61's booking horizons for rail (Eurostar ~11 months,
SNCF/Trenitalia ~4, DB up to 12/6, Renfe erratic); airport transfer buffers; and
the hard rule: **no fixed reservation on arrival day without a 3-hour buffer.**

**Luxury to camping.** "Stay where you eat" for hotels (Michelin Keys, Mr & Mrs
Smith, Design Hotels), Hipcamp / Pitchup / Canopy & Stars for the outdoors end —
with camping legs placed on relaxed market-and-picnic days near the dinner anchor,
never 45 minutes from a late reservation.

**Pacing and craft.** One anchor per half-day, district clustering, regional
meal-time customs, jet-lag day 1 kept reservation-free, a same-neighborhood
fallback for every anchor, one splurge per day balanced by markets and counters,
and a tourist-trap filter (menu photos, touts, prime-square locations).

**Verify and deliver.** Every fact checked against the official source and
date-stamped (`checked 2025-06-14 via museum site`); unconfirmed items flagged
`[VERIFY]`. The deliverable is `itinerary-<slug>-<start-date>.md`: trip frame,
day-by-day table, deadline-ordered booking checklist (platform, drop date,
confirmation #, cancellation deadline), budget mix, verification log, and open
questions — plus a custom Google Maps list of the anchors on request.

## What the agent will not do

It plans; it does not purchase. Bookings, payments, and venue contact happen on
the traveler's side (or by explicit instruction in a normal, non-plan session) —
plan mode explicitly forbids booking, reserving, purchasing, or writing trip
files until the plan is approved.

## Install

> **Zero-setup path — let DSH install it for you.** In any DSH session, just
> point it at this repository:
>
> > "Install the agent preset at
> > https://github.com/Axotopia/dsh/tree/main/vacation-planner, and verify it
> > mounts — start a session on the Vacation Planner mode. Grant Full Access to
> > the filesystem for this job."
>
> Full Access is needed only because the preset lands *outside* the session
> workspace (`%USERPROFILE%\.dsh\.agent-presets\`). There are no dependencies
> to install: the preset is YAML + one skill, and all model traffic goes through
> your existing DSH provider configuration.

Manual path — copy this folder into any preset root DSH scans:

- **Windows:** `%USERPROFILE%\.dsh\.agent-presets\vacation-planner`
- **macOS / Linux:** `~/.dsh/.agent-presets/vacation-planner`

```powershell
Copy-Item .\vacation-planner $env:USERPROFILE\.dsh\.agent-presets\vacation-planner -Recurse
```

Then pick **Vacation Planner** as the session mode in DSH.

## Use

1. Select the **Vacation Planner** preset as your session mode.
2. Frame the trip — dates, party, budget shape, dietary restrictions, splurge
   appetite, lodging style (design hotel ↔ camping). It asks only what you own
   and researches the rest.
3. Ask for the trip — e.g. *"Plan 5 days in San Sebastián in October for two:
   one splurge dinner per day, gluten-free, one night glamping in the hills"* —
   and get a day-by-day itinerary file with the booking checklist, plus map
   links. Multi-city trips fan venue/event/transit research out to subagents.

## Design notes

- **Derived from `standard`**: the tool rows are the full coding-agent toolset
  unchanged — research, not coding, is this agent's workload, and the same rows
  serve it (web tools are the maps, guides, calendars, and booking engines;
  the filesystem holds itinerary files; delegation fans research out).
- **`time-context` enabled** (15-minute refresh): a durable clock reading so
  drop dates, event calendars, and "what's open this week" anchor to today.
- **Plan mode re-aimed**: the shipped plan-mode contract's mechanics are kept
  (explore before executing, `exit_plan_mode` presentation) with the exploration
  defined as web research and execution defined as booking/writing files.
- **Realm discipline preserved** from `standard`: per-agent state (plan mode,
  compaction) stays behind entry-local isolate realms; rows that publish
  nothing sit loose, exactly as the shipped composition documents.

## Disclaimer

These presets are proof-of-concept models, not drop-in production solutions.
Review the composition (`agent.cordis.yml`), persona, and skill, and adapt them
to your use cases. Itineraries are research assistance, not reservations:
venues, events, hours, and fares change — the verification log tells you what
was checked and when, and everything flagged `[VERIFY]` needs a human check
before you rely on it.

## License

MIT — see [LICENSE](LICENSE).
