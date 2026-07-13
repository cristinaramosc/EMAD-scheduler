# EMAD Scheduler Documentation

This folder holds the official reference for the EMAD Scheduler project. It is intended for new developers and AI assistants.

## Recommended reading order

1. `docs/AI_CONTEXT.md` — the fastest entry point for understanding the project, architecture, current status, and next sprint.
2. `docs/ARCHITECTURE.md` — a detailed architecture view of the backend, frontend, domain layer, services, repositories, and routes.
3. `docs/SCORING.md` — the scoring, constraints, penalties, and tie-breaking rules that guide proposal ranking.
4. `docs/ALGORITHM.md` — the future `SchedulerGenerator` design, its inputs, outputs, planning phases, and interaction with the scheduler engine.

## Document categories

- Architecture
  - `docs/ARCHITECTURE.md`
  - `docs/AI_CONTEXT.md`
- Business rules and scoring
  - `docs/SCORING.md`
- Future algorithm and planning
  - `docs/ALGORITHM.md`

## Pending work and planning

- `docs/AI_CONTEXT.md` includes the current status and next sprint.
- `docs/ALGORITHM.md` describes the planned `SchedulerGenerator` component.
- `docs/SCORING.md` is the source of truth for constraints and scoring logic.

## Notes

- This folder is the only place where documentation should be added or updated for the sprint.
- Do not modify application code in `backend/`, `frontend/`, `tests/`, or configuration files for this documentation task.
