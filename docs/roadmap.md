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

### Remaining gaps
- **Assembly robustness.** Harden the INDRA assembly pass with multi-key deduplication, conflict resolution playbooks, provenance surfacing in the UI, and licensing checks for every upstream corpus.
- **Bibliometric depth.** Expand Semantic Scholar ingestion with richer bibliometrics (cohort metadata, funding disclosures, MeSH terms), citation-network centrality metrics, and cross-repository alerting when new cohorts land.
- **Operational hygiene.** Schedule recurring classifier retraining, publish contributor notebooks for the upgraded pipeline, and document the provenance of new signals alongside evaluation scorecards.

### Near-term focus
- Extend the INDRA-style assembly pass with deeper deduplication, provenance surfacing, and licensing reviews so downstream curators can trust merged statements at scale.
- Expand bibliometric enrichment with citation-network features, cohort metadata, study funding annotations, and refreshed Semantic Scholar fields to strengthen prioritisation signals.【F:docs/blueprint-alignment.md†L9-L40】
- Schedule recurring classifier retraining and evaluation jobs, publishing contributor notebooks that demonstrate the upgraded pipeline on representative corpora.
- Wire ingestion freshness monitors into telemetry so regression dashboards highlight staleness before researchers notice gaps.

### Delivery enablers
- Draft an RFC that defines the evidence provenance schema (fields, storage, retention) and aligns it with the governance registry.
- Pair with infrastructure to size storage and rate-limit requirements for the expanded Semantic Scholar pull jobs.
- Capture triaged licensing questions (Semantic Scholar, publisher terms, public datasets) in the governance registry for weekly review.

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

### Remaining gaps
- **Batch processing.** Automate mesh and volume conversion across Julich/HCP drops, documenting resampling strategies that keep large assets browser-friendly and versioned.
- **QA visibility.** Expose cockpit QA indicators, provenance freshness, and download readiness so curators catch geometry drift early.【F:docs/blueprint-alignment.md†L41-L80】
- **Coverage expansion.** Broaden volumetric coverage to include deep nuclei, cerebellar regions, and pediatric/adolescent variants prioritized in the blueprint.
- **Submission workflow.** Publish contributor checklists (file formats, voxel size, QC thresholds) so community submissions align with automation pipelines.

### Next steps
- Sequence mesh/volume automation alongside cockpit QA indicators so curators see asset freshness as soon as new batches land.
- Capture the agreed resampling defaults—and the roadmap for deeper nuclei/cerebellar coverage—in the atlas contributor guide to unblock community submissions.
- Stand up nightly smoke tests that render resampled assets in headless browsers to catch tiling and texture issues.
- Coordinate with the frontend team on progressive loading strategies for oversized meshes, with fallback sprites documented for legacy browsers.

### Delivery enablers
- Align with infrastructure on object-storage lifecycle policies for large geometry assets and cost alerts.
- Define QA data contracts so telemetry includes per-atlas checksum, bounding box, and coordinate frame metadata.
- Socialise a joint backlog with the cockpit design team covering indicator placement, accessibility, and localisation requirements.

## Workstream 3 – High-Fidelity Simulation Defaults
### Objectives
1. Ship reproducible builds that include PySB (Python Systems Biology), OSPSuite (Open Systems Pharmacology Suite), and The Virtual Brain (TVB) without manual intervention.
2. Maintain analytic fallbacks while exposing capability detection in the UI.

### Milestones
- **M1: Containerized toolchains.** Publish Docker images with preinstalled scientific stacks and system dependencies (Basic Linear Algebra Subprograms/Linear Algebra Package, BLAS/LAPACK) for backend workers, alongside reproducible packaging for the heavy solver stack.
- ✅ **M2: Feature toggles in API responses.** `/simulate` now includes backend/fallback metadata so cockpit controls and telemetry can reflect the executing solver.【F:backend/simulation/engine.py†L218-L502】【F:backend/api/routes.py†L212-L420】
- **M3: Continuous benchmarks.** Automate regression tests comparing analytic versus mechanistic outputs on reference scenarios and calibrate cohort defaults against social-behavioural reference studies.
- ✅ **M4: Documentation refresh.** README and deployment guides explain how to enable PySB/OSPSuite/TVB stacks locally and in hosted environments.【F:README.md†L78-L176】【F:docs/deployment-guide.md†L1-L170】

### Remaining gaps
- **Toolchain packaging.** Publish containerised toolchains (PySB, OSPSuite, TVB) with reproducible packaging for the heavy solver stack, GPU/CPU sizing guidance, and hosted deployment runbooks.
- **Benchmark automation.** Stand up automated analytic-vs-mechanistic regression benchmarks with calibrated cohort defaults informed by social-behaviour studies and animal model references.
- **Cross-scale validation.** Extend benchmarking to cross-scale social-behaviour reference tasks and document defaults inside the blueprint follow-up RFC for reproducible hand-off and reviewer sign-off.
- **Reproducible hand-offs.** Provide sample workspace exports (conda lockfiles, Docker compose stacks) so external collaborators can rerun reference simulations without bespoke setup.

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

### Remaining gaps
- **Decision support.** Ship priority scoring, inline readers, and telemetry-driven analytics that keep curators inside the cockpit and quantify review impact.
- **User research.** Run UX research on prioritisation controls, inline evidence readers, collaboration loops, and accessibility requirements before expanding the UI.
- **Integrations.** Build downstream integrations (for example, ticketing webhooks, Slack digests) once the collaboration surface stabilises and governance reviews pass.
- **Training content.** Package onboarding guides and video walkthroughs so new reviewers adopt the triage workspace quickly.

### Next steps
- Prototype lightweight priority scoring within the existing analytics harness, then validate it through scheduled UX research and telemetry experiments.
- Layer inline readers and ticketing integrations after instrumentation confirms the revised triage flow, and publish beta release notes for pilot curators.
- Stand up per-workstream dashboards that blend telemetry and qualitative research notes, closing the loop with governance stakeholders.

### Delivery enablers
- Finalise design tokens/shared components with the frontend team to accelerate cockpit iteration.
- Define telemetry schemas (events, properties, retention) and align them with observability guardrails in Workstream 5.
- Coordinate with legal/compliance on data residency requirements for embedded document readers and third-party integrations.

## Workstream 5 – Cross-Cutting Observability & Governance
### Objectives
1. Ensure new pipelines are observable and auditable.
2. Keep data governance aligned with clinical research standards.

### Current status
- ✅ **Telemetry baseline.** GraphService emits OpenTelemetry counters for research queue usage and evidence lookups, and the broader backend/worker stack honours OTLP exporters when configured.【F:backend/graph/service.py†L60-L120】【F:README.md†L117-L160】
- ✅ **Governance registry.** Data source records with audit checklists are maintained server-side and exposed via the API/governance endpoints for dashboards.【F:backend/graph/governance.py†L1-L120】【F:backend/api/routes.py†L360-L430】
- ⏳ **Automated alerts.** Alert routing/runbooks remain manual; wiring telemetry into paging and compliance reviews is future work.

### Remaining gaps
- **Alerting automation.** Automate alert routing for ingestion lag, simulation errors, atlas QA regressions, and cockpit outage signals using the emitted metrics and responder schedules.
- **Runbook maturity.** Publish runbooks, dashboard templates, and tabletop exercises that consume the new telemetry/gov APIs with clear service-level objectives (SLOs).
- **Governance registry sync.** Synchronise the governance registry with infrastructure secrets, retention policies, and licensing attestations to maintain audit readiness.
- **Compliance monitoring.** Integrate periodic privacy/ethics reviews and share metrics on retention-policy adherence.

### Next steps
- Land alert automation alongside published runbooks so telemetry guardrails activate with clear ownership paths and escalation ladders.
- Close the governance registry gaps by mapping secrets management and retention policies into the cockpit dashboards and quarterly compliance reviews.
- Align observability rollouts with Workstream 1/2 freshness indicators so end-to-end signals reach the same dashboards.

### Delivery enablers
- Partner with infrastructure to provision alert transport (PagerDuty, Slack webhooks) and secrets backends with audit trails.
- Codify the governance data model (owners, review cadence, retention) in version control and link it to the RFC tracker.
- Add synthetic monitoring checks for the public cockpit endpoints with automated issue creation when guardrails trip.

## Recommended next moves
- Drive the cross-workstream "next steps" agenda: deepen bibliometric enrichment with scheduled classifier retraining, advance the high-fidelity simulation packaging, surface atlas QA/freshness in the cockpit, and automate observability guardrails across telemetry and governance flows.
- Maintain fortnightly reviews of dependency/licensing status so remaining blockers surface early during sprint planning.
- Assign workstream leads, draft RFCs that codify remaining milestones, and publish decision logs in the governance registry.
- Stand up a shared milestone dashboard (Projects + OKRs) that highlights telemetry freshness, atlas coverage, simulation benchmark status, and UX research cadence in one view.
- Sequence licensing/infrastructure dependency reviews before sprint commitment so heavy solver packaging and Semantic Scholar ingestion land without blockers.

## Readiness checklist
- [ ] Workstream leads confirmed with weekly sync cadence on the roadmap backlog.
- [ ] RFCs drafted for assembly provenance, atlas automation, solver packaging, triage UX instrumentation, and observability guardrails.
- [ ] Licensing and infrastructure dependency reviews scheduled with governance and DevOps counterparts.
- [ ] Telemetry dashboards show ingestion freshness, atlas QA status, simulation benchmark recency, and triage UX adoption metrics.
- [ ] Contributor notebooks and onboarding guides published for each workstream’s upgraded tooling.

## Sequencing Overview
1. **Quarter 1:** Kick off Workstreams 1 and 2 to unblock richer evidence and visualization; establish telemetry foundations (Workstream 5 M1).
2. **Quarter 2:** Deliver high-fidelity simulation defaults (Workstream 3) and launch the redesigned gap triage user experience (UX) (Workstream 4 M1–M2).
3. **Quarter 3:** Complete collaboration and drill-down tooling (Workstream 4 M3–M4) and finalize governance artifacts (Workstream 5).

## Next Steps
- Assign workstream leads, draft requests for comments (RFCs) covering the remaining milestones, and line up licensing/infrastructure dependency reviews before sprint commitment.
- Track progress via the existing GitHub Projects board with quarterly objectives and key results (OKRs) aligned to the milestones above.
