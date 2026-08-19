# Shipping UI delivery contract

This contract is the handoff boundary between the Python shipping model and Claude's UI work.

## Source of truth

- Screen data: `public/data/shipping_capacity_v1.json`
- Diagnostics: `public/data/shipping_capacity_diagnostics_v1.json`
- Backtests: `public/data/shipping_capacity_backtests_v1.json`
- All three files must share the same `bundle_id`.
- The browser must not read model configuration files directly.
- The machine-readable screen map is `ui_delivery_contract` in the screen data. It supersedes hard-coded view field lists.

Claude owns layout, interaction, formatting and navigation. Python owns every shipping calculation. JavaScript must not reproduce route-cycle formulas, convert policy targets into speed changes, sum route rows into an environmental total, or replace missing values with zero.

## Environment panel under Global Fleet

Render pathway controls from `environment.pathways[]`; do not hardcode the three cards.

- `id`: stable selector (`imo_adopted`, `accelerated`, `deferred`)
- `name_ko`, `description_ko`: visible title and explanation
- `policy_status`: show whether the path is adopted or counterfactual

Filter `environment.scenarios[]` by `pathway_id`, then order by `year`. Each pathway contains 2026–2030 and is ready for a line or grouped-bar chart.

- Primary impact: `effective_dwt_loss`
- Capacity retained: `effective_service_capacity_dwt`
- Reference requirement: `baseline_required_dwt`
- Same-service requirement: `same_service_required_dwt`
- Extra requirement: `additional_required_vs_baseline_dwt`
- Uncovered gap: `capacity_gap_vs_allocated_dwt`
- Sensitivity band: the corresponding `*_range` object
- Regulatory labels: `regulatory_inputs`; do not infer them from the path name
- Ship-type bars: `ship_type_breakdown[]`; use `ship_type` for container/dry-bulk/tanker colors

The panel scope is representative modeled routes, not the full world fleet. Keep `scope` visible. `physical_allocated_dwt` is a reference denominator and should not be described as vessels demolished by regulation.

## Remaining screens

- Route service cards use `routes[].baseline` and `routes[].operational_profile`.
- The route page title is `항로 운항 선복량`; it means the modeled DWT continuously needed to serve the stated flow, not live ship positions. Render the four published tabs: all/container/dry-bulk/tanker.
- Compare global ship types using `fleet.fleet_by_type[].dwt`. Container service class belongs in its own TEU range from `routes[].reference_size`; no global container-TEU total is currently published, so do not create one in the UI.
- Chokepoint observed cards use `chokepoints_live` and `live_display`; the UI does not interpolate history.
- Chokepoint simulator values come only from `ui_scenario_grid.rows[]`. Match a row by `base_scenario_id`, `closure_pct`, and `duration_days`.
- Render `summary.ship_type_breakdown[]` for container/dry-bulk/tanker comparisons. Do not sum the route rows in the browser.
- Use `ui_delivery_contract.views.chokepoint_detail.labels_ko` for the control and backlog labels. The duration is the duration of the assumed constraint; the published backlog is the unserved cargo remaining at the fixed 28-day analysis horizon.
- Use `chokepoints[].risk_context` for the commercial/operational explanation. It distinguishes security-driven constraints from Panama's water-availability/traffic-management case.
- Scenario cards use `scenario_summary`; do not recompute them from route rows.

## Release gates

1. Validate the screen JSON against `schemas/shipping_capacity_v1.schema.json`.
2. Run the Python golden contract; every UI-visible route and environment value must equal diagnostics.
3. If a required field is absent, render an unavailable state and report the contract gap. Do not create a UI estimate.
4. Keep model/data changes out of Claude's UI commit unless Codex explicitly provides a contract revision.
