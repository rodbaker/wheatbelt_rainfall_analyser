# Decision: SILO Variable Expansion — No (2026-05-18)

## Status

**No.** WRA will not expand SILO ingest beyond the current operational
contract of rainfall (R), min temperature (N), and max temperature (X) at
this time.

This is a decision record, not an implementation plan.

## Context

The question arose during a session reviewing the SILO ingest mechanism. The
SILO PPD S3 mirror bundles all variables by default, which prompted the
broader question: would having the full variable set benefit future crop
forecasting?

Six additional daily variables are present in SILO and partially referenced
in WRA code:

- V — vapour pressure (hPa)
- J — solar radiation (MJ/m²)
- E — pan evaporation (mm)
- H — relative humidity at Tmax (%)
- G — relative humidity at Tmin (%)
- F — FAO-56 reference ET (mm)

The agronomic case is plausible — humidity for disease-window and
heat-stress refinement, ET for water-balance dry spells — but the timing
and operational cost do not justify acting now.

## Reasons for the No

1. **Quality-checker blast radius.** Enabling extra variables in
   `config/silo_sources.yaml` would cause `DataQualityChecker` to assess and
   filter every configured variable, not just R/N/X. See
   `src/agents/silo_wrangler/quality_checker.py` lines 56 and 272. A missing
   or poor evaporation/RH field can reduce station confidence or null
   values even when R/N/X are clean — changing station acceptance
   behaviour, not a free config flip.

2. **Storage path discards extra variables today.** The DuckDB write path
   explicitly selects only `station_id, date, min_temp, max_temp, rainfall`
   plus quality columns and `ingested_at` before upsert at
   `src/agents/silo_wrangler/run_ingest.py:228` and `:348`. The DuckDB schema
   at `src/data/duckdb_storage.py:49` carries only R/N/X. "Pull now and
   accumulate" is false until schema, upsert, and export are changed.

3. **API client readiness is partial.** `data_processor.py:89` maps
   V/J/D/E/H/G/F/M, but `api_client.validate_response_data()` at
   `src/agents/silo_wrangler/api_client.py:224` only validates R/X/N/V/J/H/G
   and omits E/F/D/M. End-to-end readiness needs verification at every
   layer.

4. **Disease watch is not threshold-driven.** The section in
   `src/agents/insight_publisher/report_generator.py:416` triggers on
   frost/rainfall event presence, not on disease-favourable weather
   conditions. Pathogen descriptions in `data/meta/wa_seasonal_context.yaml`
   are prose, not machine thresholds. Enabling H/G alone would not light
   up disease alerts without separate event-detector work.

5. **"Full variable set" is underspecified.** The config TODOs at
   `config/silo_sources.yaml:17` list V/J/E/H/G. F is mapped in code but
   not in config; D and M are also mapped. A future spike must define a
   narrow candidate set with a stated purpose per variable, not adopt
   "everything SILO offers."

## Operational posture this decision preserves

WRA operates in evidence-led mode. Capability is expanded when an analyst
hits friction that justifies a specific variable, not in anticipation of
future needs. The current operational contract is R/N/X. The rainfall
handoff v1.0 contract in `docs/rainfall_handoff_v1_contract.md` documents
the canonical outputs that downstream consumers depend on; that contract is
unaffected by this decision.

## What would change the answer

A future spike would be considered only when both conditions hold:

- The manual-review cycle (see `~/.claude/skills/acm-wra-manual-review/`)
  surfaces a recurring analyst-flagged gap that maps directly to a specific
  variable — e.g. a disease alert that did not fire, or a heat narrative
  the analyst would have written differently with humidity context.
- The gap is commercially material to reporting, not just methodologically
  interesting.

If/when that happens, the spike must be staged and separately approved:

1. Define a narrow candidate set by purpose (H/G for disease and
   frost-microclimate; F or E for water-balance; V only for VPD;
   skip J unless a radiation use case appears).
2. Read-only sample retrieval first — 5–10 WA stations, 30–90 days, no
   schema changes — to compare completeness, quality flags, and value
   plausibility.
3. Only on good sample quality, add storage behind a separate approval:
   schema migration, upsert/export updates, quality checker adjusted so
   optional variables do not exclude otherwise valid stations, regression
   test proving existing R/N/X event counts do not change.
4. Wire event-detector logic last — disease windows, humidity-aware heat,
   ET-aware dry spells — after the triggering friction recurs with the
   new data available.

## Files referenced (read-only — no changes made by this decision)

- `config/silo_sources.yaml`
- `src/agents/silo_wrangler/quality_checker.py`
- `src/agents/silo_wrangler/run_ingest.py`
- `src/agents/silo_wrangler/api_client.py`
- `src/agents/silo_wrangler/data_processor.py`
- `src/data/duckdb_storage.py`
- `src/agents/insight_publisher/report_generator.py`
- `data/meta/wa_seasonal_context.yaml`
- `docs/rainfall_handoff_v1_contract.md`

## Revisit trigger

Recurrence of the same variable-related friction across multiple
manual-review cycles. Until then, R/N/X remains the operational ingest
contract.
