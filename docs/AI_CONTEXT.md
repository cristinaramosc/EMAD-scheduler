# EMAD Scheduler AI Context

This file is the fastest way for an AI assistant to understand the EMAD Scheduler project in under 10 minutes.

## Project purpose

EMAD Scheduler is a timetable planning and validation system for the Escola Municipal d'Art i Disseny. It supports teaching requirements, generates candidate block distributions, and validates schedules for room and teacher conflicts. The system is built as a backend API with a separate frontend UI.

## Current architecture

### Frontend

- Located in `frontend/`.
- Built with Vite and React.
- The frontend consumes backend APIs but is not part of the current documentation sprint.
- It is separate from domain logic, database access, and scheduler generation.

### Backend

- Located in `backend/`.
- FastAPI exposes routes under `backend/routes`.
- The backend contains domain adapters, services, an in-memory repository for teaching requirements, block generation utilities, and a scheduler validation engine.
- There is no dependency on the frontend or FastAPI in the core domain model definitions.

### SchedulerEngine

- Implemented under `backend/scheduler_engine/engine.py`.
- Stores a `Schedule` and validates it against constraints.
- Constraint implementations live in `backend/scheduler_engine/constraints/`.
- `SchedulerEngine` is strictly a validator and runtime state holder.
- It does not generate proposals or assign time slots.

### RequirementService

- Implemented in `backend/services/requirement_service.py`.
- Responsible for CRUD operations on `TeachingRequirement` and for driving block generation.
- Converts payloads into domain objects and delegates persistence to `RequirementRepository`.

### RequirementRepository

- Implemented in `backend/repositories/requirement_repository.py`.
- In-memory store for `TeachingRequirement` instances.
- Supports `create`, `get`, `list`, `update`, and `delete`.
- Returns deep copies to avoid accidental mutation.

### TeachingRequirement

- Domain model in `backend/scheduler_engine/models/teaching_requirement.py`.
- Represents the source of truth for a teaching requirement.
- Holds group, subject, teacher, weekly hours, day constraints, block durations, and scheduling preferences.
- Validations run on construction.

### TeachingBlock

- Domain model in `backend/models/teaching_block.py`.
- Represents a duration block for a requirement before temporal assignment.
- Includes `duration`, `order`, optional preferred room/teacher, and metadata.
- It does not know day, start time, or room assignment.

### BlockGenerator

- Implemented in `backend/services/block_generator.py`.
- Generates candidate block distributions for a `TeachingRequirement`.
- Produces lists of `TeachingBlock` values.
- It never assigns time slots or days.

### SchoolCalendar

- Implemented in `backend/scheduler_engine/models/school_calendar.py`.
- Defines available days, periods per day, breaks, and holidays.
- Provides `periods_for_day()` and `is_period_lective()`.
- It is the source of temporal availability for future scheduling.

### ScheduleProposal

- Implemented in `backend/scheduler_engine/models/schedule_proposal.py`.
- Represents a complete proposed schedule before acceptance.
- Contains `id`, `activities`, `score`, `conflicts`, `warnings`, and optional `metadata`.
- It is independent of FastAPI, frontend, and database.

### SchedulerGenerator (planned)

- Not implemented yet.
- Future component that will convert `TeachingBlock` distributions into `ScheduleProposal` objects.
- Will use `SchoolCalendar` availability and produce candidate proposals for validation.

## Planning pipeline

TeachingRequirement
        ↓
RequirementService
        ↓
RequirementRepository
        ↓
BlockGenerator
        ↓
TeachingBlock
        ↓
SchedulerGenerator
        ↓
ScheduleProposal
        ↓
SchedulerEngine
        ↓
Conflict Report

## Golden Rules

- Never move business logic into FastAPI routers.
- SchedulerEngine only validates.
- SchedulerGenerator generates proposals.
- BlockGenerator never assigns time slots.
- TeachingRequirement is the source of truth for requirements.
- SchoolCalendar defines available slots and lective periods.
- Avoid duplicated domain models.
- Keep the architecture modular.
- Keep domain models independent of frontend, FastAPI, and database concerns.

## Current status

### Implemented

- TeachingRequirement
- TeachingBlock
- Activity
- Schedule
- SchoolCalendar
- TimeSlot
- ScheduleProposal
- RequirementService
- RequirementRepository
- BlockGenerator
- SchedulerEngine
- FastAPI routes for requirements, activities, teachers, scheduler validation and runtime state

### In progress

- BlockGenerator exists and is tested. The generator is part of the implemented pipeline, but the scheduling proposal generation path is still pending.

### Planned

- SchedulerGenerator (temporal proposal production)
- Ranking and scoring of proposals based on conflicts, warnings and soft constraints

## Current project structure

Add new domain models under `backend/scheduler_engine/models/`.

Add new services under `backend/services/`.

Add new repository adapters under `backend/repositories/`.

Add new router endpoints under `backend/routes/` only for API exposure; do not place domain logic in routers.

Keep scheduler validation logic under `backend/scheduler_engine/`.

## Important decisions

- The primary schedule view is per group.
- The scheduler engine is a validation engine, not a proposal engine.
- A compatibility shim exists to support imports under `scheduler_engine.*`.
- Domain models should be re-used and not duplicated across layers.

## Next sprint

The next implementation task is `SchedulerGenerator`.

It should take `TeachingBlock` distributions, use `SchoolCalendar` availability, build `ScheduleProposal` objects, and hand those proposals to `SchedulerEngine` for validation. It must not replace the current validation engine.
