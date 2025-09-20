# Neuropharm Sim Lab Contributor Guardrails

This file defines the base expectations for every change in this repository.
All contributors **must** follow the rules below and document any deviation in
review notes.

## Repository-wide expectations
- Keep commits focused and explain *why* as well as *what* in your PR body.
- Prefer incremental, well-tested changes; avoid rebasing or rewriting shared
  history.
- Follow Python typing and linting best practices; avoid introducing unused or
  dead code.
- Every pre-merge run must include the following commands and any project-wide
  equivalents you introduce:
  - `python -m compileall backend/main.py`
  - `pytest`
  - `npm test -- --watch=false` (if frontend assets are impacted)
- Update documentation, changelogs, and configuration defaults alongside code
  changes that alter behavior.

## Directory-specific expectations

### `backend/`
- Provide input validation and meaningful error messages for new endpoints,
  scripts, or utilities.
- Maintain citation hygiene in comments, docstrings, and generated outputs.
  Reference data sources with persistent identifiers (e.g., DOI or URL).
- Exercise defensive programming: add tests that cover success, failure, and
  edge conditions.
- Run targeted backend checks in addition to the repository-wide commands when
  touching this directory (e.g., module-level compile checks, type checking).

### `docs/` and `README.md`
- Write in clear, plain language accessible to new contributors and external
  collaborators.
- Prioritize task-oriented explanations and cross-link to deeper references.
- Keep examples up to date; validate that commands still work as written.
- Include citations for scientific claims, but avoid jargon where simpler terms
  suffice. Explain acronyms on first use.

## Extending these guardrails
Nested folders may include their own `AGENTS.md` files. Those files can refine
or tighten the rules above, but they must not relax repository-wide
requirements.
