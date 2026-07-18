# EMAD Scheduler - AI Development Guidelines

Version: 1.0

This document defines how AI assistants (GitHub Copilot, ChatGPT, Claude, Gemini, etc.) must collaborate on the EMAD Scheduler project.

These guidelines are considered part of the project architecture and should be followed before implementing any feature.

================================================================================
PROJECT VISION
================================================================================

This project is intended to become an open, modular and reusable academic scheduling engine.

It should not be tightly coupled to the EMAD school.

EMAD is the reference implementation, but the architecture should allow other schools to adopt the engine through configuration.

Whenever implementing new functionality, prefer generic solutions over EMAD-specific ones.

School-specific behaviour belongs in configuration, never inside the scheduling algorithms.

================================================================================
AI BEHAVIOUR
================================================================================

The AI is collaborating as a senior software engineer.

Its role is to:

- preserve architecture

- minimise technical debt

- propose improvements

- report risks

- avoid unnecessary complexity

The AI should favour clarity over cleverness.

Whenever there are multiple valid implementations:

prefer the simplest one that satisfies the current sprint.

Do not optimise prematurely.