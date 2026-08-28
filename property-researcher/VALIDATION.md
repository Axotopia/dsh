# Validation Summary

What has been field-verified, on Washington State public records, during the build
and hardening of this preset. This is a summary; full incident narratives are not
published.

## Environments

- DSH 0.1.1-rc.2, Windows 10/11-class workstations, Node ≥ 20
- Multi-session validation on three AHJ families: **Seattle**, **King County**,
  **Chelan County** (incorporated-city, county-assessor, and unincorporated-county
  surfaces respectively)

## Verified capabilities

| Capability | Evidence |
|---|---|
| Preset mounting & tool surface | Roster-service mount validation; MCP handshake + all 16 browser tools enumerated over stdio |
| Structured GIS retrieval | Live ArcGIS REST point-queries returning zone polygons, ordinance numbers, effective-date epochs, hazard overlays, flood zones, snow-load contours, UGA boundaries |
| Regulatory-currency discipline | A parcel whose county assessor label printed a superseded designation while the city FeatureServer showed the operative ordinance (later republication, effective date epoch-verified) — contradiction caught and logged rather than averaged |
| TLS transport fallback | Session-scoped Windows schannel death reproduced; Node/OpenSSL retry path restored fetching; doctrine codified and exercised in field runs |
| WAF/challenge handling | Challenge bodies captured and treated as terminal on fetch paths; a county-code republication that 403'd plain fetches was rendered and quoted section-by-section through the **browser tier in production** |
| Certificate-anomaly handling | Expired TLS certificate on a county ArcGIS host; per doctrine, verification was never disabled — the authority's own alternate port served the same records, and the anomaly was flagged in the report's provenance |
| Adversarial interpretation | Blue/Red team dispute over sub-minimum plat lot legality resolved by the arbiter against verbatim nonconforming-lot code text; a "threshold killer" framing rebutted with the operative provision |
| Gut Check vs Deep Research | Fast screen correctly identified a parcel warranting deeper research (stale labels + unresolved lot legality + hazard overlay); Deep Research then resolved the same question with verbatim code, agency tracks, cost envelope, and deadlock declarations |
| Honest deadlocks | Font-encoded PDF conditions text (unextractable) ruled DEADLOCK and routed to a named AHJ contact action instead of being guessed |
| Grading hygiene under audit | Cross-session audit of outputs caught owner-currency staleness, figure-class conflation, and unproven premises; fixes codified and verified in subsequent runs |
| PDF generation | Markdown→PDF tool live (headless Edge/Chrome, local rendering); distribution gate exercised in sessions |

## Known limits

- Validated surfaces are Washington State; other states/countries work through the
  discovery ladder but are not yet field-proven.
- Single vision-pass transcriptions are capped at `Probable`; `Confirmed` requires a
  second agreeing pass or structured-source corroboration.
- The browser tier requires a visible browser window; fully headless operation is
  deliberately unsupported (see security model in the README).
