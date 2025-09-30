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

### Milestones
- **M1: spaCy/scispaCy-powered extraction.** Package lightweight models in `backend/text_mining` with optional graphics processing unit (GPU) support; implement entity linking against ChEMBL and Medical Subject Headings (MeSH) vocabularies.
- **M2: INDRA-style assembly layer.** Normalize extracted relations into causal event frames, deduplicate with hash-based identifiers, and store provenance metadata in the graph service.
- **M3: Semantic Scholar ingestion.** Extend the ingestion plan to fetch work metadata, citations, and abstracts through their application programming interface (API); reconcile identifiers with OpenAlex entries.
- **M4: Evidence quality scoring.** Train heuristics or classifiers for study design, sample size, and species tags to prioritize high-quality literature in dashboards.

### Success Criteria
- Coverage metrics comparing regex fallback vs. NLP pipeline on a held-out corpus.
- Graph nodes contain labeled relation types (activation, inhibition, binding) with grounded participants.
- Ingestion jobs tolerate intermittent API failures through backoff and checkpointing.

### Dependencies & Notes
- Confirm licensing of Semantic Scholar data for redistribution.
- Provide sample notebooks demonstrating the assembly pipeline for contributors.
- The repository now includes a dependency-matcher-based extractor and
  INDRA-lite assembly stage behind optional scispaCy models; see the README for
  installation guidance and fallback behaviour.

## Workstream 2 – Expanded Atlas and Geometry Support
### Objectives
1. Broaden anatomical coverage beyond the current limbic/prefrontal set.
2. Ensure frontend visualizations default to real coordinates instead of synthetic hashes.

### Milestones
- **M1: Source expansion.** Add ingestion for the Human Connectome Project and Julich-Brain atlases, normalizing to the Montreal Neurological Institute (MNI152) template and the Allen Common Coordinate Framework (CCF) systems.
- **M2: Mesh and volume processing.** Automate conversion to Neuroimaging Informatics Technology Initiative (NIfTI) and Geometry Format for the Informatics (GIfTI) assets stored in object storage, tagged with provenance identifiers.
- **M3: Frontend registry.** Replace hash fallbacks by introducing an atlas lookup API that returns best-available geometry per region with confidence flags.
- **M4: Quality assurance (QA) harness.** Build visual regression scripts (e.g., Cypress or Playwright) that snapshot key regions in NiiVue to catch alignment regressions.

### Success Criteria
- ≥80% of canonical regions requested by the cockpit render real meshes/volumes.
- Atlas API includes provenance metadata (source, resolution, license) for every region served.

### Dependencies & Notes
- Coordinate with the infrastructure team on storage costs for large volumetric assets.
- Document resampling strategies to keep assets within browser-friendly sizes.

## Workstream 3 – High-Fidelity Simulation Defaults
### Objectives
1. Ship reproducible builds that include PySB (Python Systems Biology), OSPSuite (Open Systems Pharmacology Suite), and The Virtual Brain (TVB) without manual intervention.
2. Maintain analytic fallbacks while exposing capability detection in the UI.

### Milestones
- **M1: Containerized toolchains.** Publish Docker images with preinstalled scientific stacks and system dependencies (Basic Linear Algebra Subprograms/Linear Algebra Package, BLAS/LAPACK) for backend workers.
- **M2: Feature toggles in API responses.** Extend `/simulate` metadata to report which solvers were used and whether fallbacks triggered.
- **M3: Continuous benchmarks.** Automate regression tests comparing analytic versus mechanistic outputs on reference scenarios.
- **M4: Documentation refresh.** Update README and deployment guides with turnkey instructions for enabling high-fidelity simulations locally and in cloud targets.

### Success Criteria
- Continuous integration (CI) job runs mechanistic simulations on at least one hosted runner each week.
- Users can opt into or out of heavy toolchains via configuration without code changes.

### Dependencies & Notes
- Evaluate licensing and distribution constraints for OSPSuite within published containers.
- Coordinate with infrastructure teams to size graphics processing unit (GPU)/central processing unit (CPU) requirements for production deployments.

## Workstream 4 – Gap Triage & Curation Experience
### Objectives
1. Transform the gap dashboard from a text list into an actionable triage workspace.
2. Surface literature follow-up and collaboration hooks within the cockpit.

### Milestones
- **M1: User experience (UX) research and design.** Conduct curator interviews, prototype heatmaps, priority queues, and saved views; validate flow with representative users.
- **M2: Prioritization engine.** Add backend scoring that combines evidence strength, novelty, and clinical relevance; expose filters and sorting APIs.
- **M3: Collaboration features.** Implement assignment, status tracking, and comment threads linked to each gap, with optional notifications.
- **M4: Literature drill-down.** Embed inline readers (portable document format/Text Encoding Initiative snippets) and “send to notebook” export actions to streamline follow-up.

### Success Criteria
- Curators can complete end-to-end triage workflows without leaving the app.
- Usage analytics show decreased time-to-triage and higher follow-up completion rates post-launch.

### Dependencies & Notes
- Partner with design on accessibility and color-contrast compliance.
- Consider integrating with existing tracking tools (e.g., Linear, Jira) via webhooks.

## Workstream 5 – Cross-Cutting Observability & Governance
### Objectives
1. Ensure new pipelines are observable and auditable.
2. Keep data governance aligned with clinical research standards.

### Milestones
- **M1: Telemetry baseline.** Instrument ingestion, simulation, and atlas services with OpenTelemetry traces and structured logs.
- **M2: Data governance checklist.** Document data lineage, retention, and consent considerations for each new source.
- **M3: Automated alerts.** Configure monitors for ingestion lag, simulation failures, and frontend asset drift.

### Success Criteria
- On-call runbooks cover all new integrations with clear remediation steps.
- Compliance review sign-off before expanding atlas or literature datasets into protected environments.

## Sequencing Overview
1. **Quarter 1:** Kick off Workstreams 1 and 2 to unblock richer evidence and visualization; establish telemetry foundations (Workstream 5 M1).
2. **Quarter 2:** Deliver high-fidelity simulation defaults (Workstream 3) and launch the redesigned gap triage user experience (UX) (Workstream 4 M1–M2).
3. **Quarter 3:** Complete collaboration and drill-down tooling (Workstream 4 M3–M4) and finalize governance artifacts (Workstream 5).

## Next Steps
- Assign workstream leads and draft requests for comments (RFCs) detailing technical designs.
- Schedule dependency reviews (licensing, infrastructure capacity) before sprint commitment.
- Track progress via the existing GitHub Projects board with quarterly objectives and key results (OKRs) aligned to the milestones above.
