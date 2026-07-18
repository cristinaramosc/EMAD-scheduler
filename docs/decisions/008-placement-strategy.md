# ADR 008 - Placement Strategy

## Status

Accepted

## Context

The scheduler currently uses a greedy placement algorithm.

With the official EMAD FET dataset, the engine successfully schedules 343 of 345 activities.

Analysis shows that the remaining two activities are not impossible to place. Instead, their feasible slots are consumed by earlier greedy decisions.

Changing the placement order allows these activities to be scheduled, but causes different activities to remain unscheduled.

This indicates a limitation of the greedy strategy rather than a bug or missing constraint.

## Decision

Version 1 will keep the greedy placement algorithm as the primary scheduling strategy.

Instead of introducing full backtracking, the scheduler will implement a bounded repair phase that attempts to relocate a small number of already placed activities in order to schedule the remaining ones.

The repair phase must:

- remain deterministic
- have bounded execution time
- preserve existing scheduler architecture
- stop as soon as an improvement is found

## Rationale

The greedy algorithm already produces a timetable covering more than 99% of activities.

Full search or unrestricted backtracking would significantly increase implementation complexity and execution time without evidence that it is necessary for EMAD datasets.

A bounded repair phase offers a good balance between simplicity and scheduling quality.

## Consequences

Pros

- Simple implementation.
- Predictable execution time.
- Minimal architectural impact.
- Higher scheduling success rate.

Cons

- Does not guarantee a globally optimal timetable.
- Some datasets may still require more advanced search in the future.

## Future

If future real datasets show that bounded repair is insufficient, more advanced search strategies (backtracking, local search, tabu search, etc.) may be evaluated.