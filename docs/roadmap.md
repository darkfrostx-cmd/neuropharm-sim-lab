# Blueprint Completion Roadmap

## Purpose
This roadmap translates the outstanding blueprint gaps into concrete, staged workstreams. It assumes the current backend orchestration, ingestion scaffolding, embedding-driven gap finder, simulation toggles, and cockpit user interface (UI) described in the blueprint are in place. Each initiative below lists objectives, first milestones, success criteria, and cross-team dependencies so contributors can plan coordinated releases.

## Guiding Principles
- **Scientific grounding.** Expand literature and atlas coverage using sources with clear licensing and persistent identifiers. Align entity resolution across pipelines.
- **Progressive enhancement.** Maintain existing fallbacks while layering richer functionality, and gate heavier stacks behind feature flags until deployment stories are proven.
- **User-centered evidence curation.** Keep gap detection explainable and actionable by curators; expose provenance and rationale across workflows.

## Workstream 1 – Robust Literature Assembly
### Objectives
1. Replace regex-only extraction with production-grade natural language processing (NLP) that yields grounded relations.
2. Integrate multi-source bibliometrics so evidence, gaps, and trends draw from a wider corpus.

### Current status
- ✅ **M1: spaCy/scispaCy-powered extraction.** Lightweight spaCy 3.7/scispaCy 0.5.4 models and entity linking are now packaged behind the `text-mining` extra with installation guidance in the README and deployment notes.【F:backend/pyproject.toml†L30-L45】【F:README.md†L58-L116】
- ✅ **M4: Evidence quality scoring.** The metadata heuristics ship with an in-repo logistic classifier, exposing probability-weighted quality summaries through the API and simulation adapter.【F:backend/graph/evidence_quality.py†L1-L214】【F:backend/graph/evidence_classifier.py†L1-L139】【F:backend/api/schemas.py†L360-L455】
- ⏳ **M2: INDRA-style assembly layer.** Baseline assembly exists, but roadmap follow-up will extend deduplication and provenance surfacing for larger corpora.【F:backend/graph/ingest_indra.py†L1-L140】
- ⏳ **M3: Semantic Scholar ingestion.** Client scaffolding is present; enriching bibliometrics and citation graph features remains active work.【F:backend/graph/service.py†L320-L384】

### Near-term focus
- Expand bibliometric enrichment with citation-network features, cohort metadata, and study funding annotations to strengthen prioritisation signals.【F:docs/blueprint-alignment.md†L9-L40】
- Schedule periodic classifier re-training/evaluation jobs and publish sample notebooks that show the upgraded pipeline on representative corpora.

### Dependencies & Notes
- Confirm licensing of Semantic Scholar data for redistribution.
- Provide sample notebooks demonstrating the assembly pipeline for contributors.
- Maintain the regex fallback for environments without spaCy/scispaCy, and document the accuracy trade-offs when the classifier is disabled.

## Workstream 2 – Expanded Atlas and Geometry Support
### Objectives
1. Broaden anatomical coverage beyond the current limbic/prefrontal set.
2. Ensure frontend visualizations default to real coordinates instead of synthetic hashes.

### Current status
- ✅ **M1: Source expansion.** Human Connectome Project and Julich-Brain sample overlays now ship with provenance metadata and ingestion wiring, expanding the atlas catalogue beyond the initial Harvard-Oxford/Allen set.【F:backend/atlas/assets/hcp_atlas_sample.json†L1-L120】【F:backend/atlas/assets/julich_atlas_sample.json†L1-L130】【F:backend/graph/ingest_atlases.py†L1-L220】
- ✅ **M4: Quality assurance harness.** A geometry QA helper validates coordinates/metadata, and regression tests guard atlas ingestion flows.【F:backend/atlas/qa.py†L1-L80】【F:backend/tests/test_atlas_geometry.py†L1-L120】【F:backend/tests/test_atlas_overlays.py†L1-L140】
- ⏳ **M2: Mesh and volume processing.** Conversion tooling exists for current assets; future work should automate batch processing for the wider Julich/HCP repositories.
- ⏳ **M3: Frontend registry.** The API surfaces overlays, but cockpit indicators for QA status/confidence remain to be built.

### Next steps
- Expose QA verdicts and provenance freshness within the cockpit to alert curators when geometry drifts.【F:docs/blueprint-alignment.md†L41-L80】
- Broaden volumetric coverage to include deep nuclei and cerebellar regions prioritized in the blueprint.
- Document resampling strategies to keep large meshes browser-friendly and coordinate with infrastructure on storage quotas.

## Workstream 3 – High-Fidelity Simulation Defaults
### Objectives
1. Ship reproducible builds that include PySB (Python Systems Biology), OSPSuite (Open Systems Pharmacology Suite), and The Virtual Brain (TVB) without manual intervention.
2. Maintain analytic fallbacks while exposing capability detection in the UI.

### Milestones
- **M1: Containerized toolchains.** Publish Docker images with preinstalled scientific stacks and system dependencies (Basic Linear Algebra Subprograms/Linear Algebra Package, BLAS/LAPACK) for backend workers.
- ✅ **M2: Feature toggles in API responses.** `/simulate` now includes backend/fallback metadata so cockpit controls and telemetry can reflect the executing solver.【F:backend/simulation/engine.py†L218-L502】【F:backend/api/routes.py†L212-L420】
- **M3: Continuous benchmarks.** Automate regression tests comparing analytic versus mechanistic outputs on reference scenarios.
- ✅ **M4: Documentation refresh.** README and deployment guides explain how to enable PySB/OSPSuite/TVB stacks locally and in hosted environments.【F:README.md†L78-L176】【F:docs/deployment-guide.md†L1-L170】

### Success Criteria
- Continuous integration (CI) job runs mechanistic simulations on at least one hosted runner each week.
- Users can opt into or out of heavy toolchains via configuration without code changes.
- Social-processing pathways (oxytocin, cholinergic BLA, vasopressin) remain calibrated across analytic and mechanistic backends.

### Solver capability matrix

| Layer        | Primary backend (default) | High-fidelity backend | Fallbacks surfaced via `/simulate` | Notes |
|--------------|---------------------------|-----------------------|------------------------------------|-------|
| Molecular cascade | SciPy ODE integrator with analytic guard rails | PySB via `pysb` if installed | PySB import/runtime errors fall back to SciPy and are reported under `engine.fallbacks.molecular` | Controlled through the `MOLECULAR_SIM_BACKEND` environment variable. |
| PK/PD        | Two-compartment IVP model (`scipy.integrate`) | OSPSuite Python API (requires Azure Artifacts wheel) | When OSPSuite is unavailable the engine records `ospsuite:<error>` and retains deterministic trajectories. | Provide `OSPSUITE_INDEX_URL`/`OSPSUITE_WHEEL_URL` at install time to opt in. |
| Circuit      | SciPy-based network solver | The Virtual Brain (`tvb-library`) | Failed TVB runs cascade to SciPy with annotated fallback entries. | `CIRCUIT_SIM_BACKEND` toggles between analytic, SciPy, or TVB modes. |

Every `/simulate` response now includes an `engine.backends` map and a `engine.fallbacks` dictionary so the cockpit and downstream analytics can display which solver executed and whether guard rails fired.

### Dependencies & Notes
- Evaluate licensing and distribution constraints for OSPSuite within published containers.
- Coordinate with infrastructure teams to size graphics processing unit (GPU)/central processing unit (CPU) requirements for production deployments.

## Workstream 4 – Gap Triage & Curation Experience
### Objectives
1. Transform the gap dashboard from a text list into an actionable triage workspace.
2. Surface literature follow-up and collaboration hooks within the cockpit.

### Current status
- ✅ **Collaboration foundation.** Research queue endpoints now support assignments, due dates, watcher management, checklists, and audit logs surfaced through the cockpit.【F:backend/graph/gap_state.py†L1-L220】【F:backend/api/routes.py†L330-L420】【F:backend/tests/test_api_integration.py†L150-L240】
- ⏳ **UX depth.** Priority scoring and inline document readers remain on the roadmap; design exploration and analytics instrumentation are pending.

### Next steps
- Run UX research to validate prioritisation controls and comment workflows before expanding the UI.
- Integrate usage analytics (leveraging the observability stack) to measure triage efficiency improvements once the richer experience ships.
- Explore integrations with existing ticketing tools via webhook adapters once the collaboration surface stabilises.

## Workstream 5 – Cross-Cutting Observability & Governance
### Objectives
1. Ensure new pipelines are observable and auditable.
2. Keep data governance aligned with clinical research standards.

### Current status
- ✅ **Telemetry baseline.** GraphService emits OpenTelemetry counters for research queue usage and evidence lookups, and the broader backend/worker stack honours OTLP exporters when configured.【F:backend/graph/service.py†L60-L120】【F:README.md†L117-L160】
- ✅ **Governance registry.** Data source records with audit checklists are maintained server-side and exposed via the API/governance endpoints for dashboards.【F:backend/graph/governance.py†L1-L120】【F:backend/api/routes.py†L360-L430】
- ⏳ **Automated alerts.** Alert routing/runbooks remain manual; wiring telemetry into paging and compliance reviews is future work.

### Next steps
- Publish runbooks and dashboard templates that consume the new telemetry/gov APIs.
- Automate alerting for ingestion lag, simulation errors, and atlas QA regressions using the emitted metrics.
- Synchronise the governance registry with infrastructure secrets/retention policies to maintain audit readiness.

## Sequencing Overview
1. **Quarter 1:** Kick off Workstreams 1 and 2 to unblock richer evidence and visualization; establish telemetry foundations (Workstream 5 M1).
2. **Quarter 2:** Deliver high-fidelity simulation defaults (Workstream 3) and launch the redesigned gap triage user experience (UX) (Workstream 4 M1–M2).
3. **Quarter 3:** Complete collaboration and drill-down tooling (Workstream 4 M3–M4) and finalize governance artifacts (Workstream 5).

## Next Steps
- Assign workstream leads and draft requests for comments (RFCs) detailing technical designs.
- Schedule dependency reviews (licensing, infrastructure capacity) before sprint commitment.
- Track progress via the existing GitHub Projects board with quarterly objectives and key results (OKRs) aligned to the milestones above.
