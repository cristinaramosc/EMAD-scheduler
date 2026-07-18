"""Adapter module exposing the domain TeachingRequirement model.

This file avoids duplicating models: it re-exports the domain class
implemented under `scheduler_engine.models` so other parts of the backend
can import from `backend.models` as requested by the architecture.
"""
try:
	from backend.scheduler_engine.models.teaching_requirement import TeachingRequirement
except ModuleNotFoundError:  # pragma: no cover
	from scheduler_engine.models.teaching_requirement import TeachingRequirement

__all__ = ["TeachingRequirement"]
