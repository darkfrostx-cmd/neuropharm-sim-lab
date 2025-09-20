# Agent Guidelines

These instructions cover the entire repository.

## Required checks
- Run `python -m compileall backend/main.py` before submitting any changes that touch the backend.

## Backend expectations
- Keep receptor-normalisation logic in `backend/main.py` reusable; prefer top-level helpers rather than nesting new functions inside route handlers.
- Preserve the `ReceptorSpec` validation guardrails (occupancy range and allowed mechanisms). If you need different behaviour, update the validator rather than bypassing it.

## Documentation
- Update the README whenever you change how someone runs the project (desktop or mobile instructions must stay accurate and easy to follow).
