# EMAD Scheduler Scoring

This document describes the scoring model used to rank schedule proposals.

## Hard constraints

Hard constraints are mandatory rules that cannot be violated. Any schedule proposal that breaks a hard constraint must be marked as invalid or penalized heavily.

Examples of hard constraints:

- Teacher conflict: a teacher cannot be assigned to more than one activity at the same time.
- Room conflict: a room cannot host more than one activity at the same time.
- Requirement minimum/maximum days: a requirement must be split across the allowed number of days.
- Block duration limits: each generated block must respect minimum block duration and maximum consecutive hours.
- Availability: a slot must be lective and not blocked by `SchoolCalendar` breaks.
- **Group quarter-pair conflict**: for a given parent group, a timeslot may only be shared between exactly two subjects, and only when one is marked `1Q` and the other `2Q` (suffix on the group name or, failing that, on the subject name — see `quarter_utils.py`). Two `1Q` subjects can never share a slot, two `2Q` subjects can never share a slot, and a shared slot can never hold more than one activity from each quarter. A subject with no compatible `1Q`/`2Q` counterpart is simply scheduled alone. Enforced both at placement time (`placement_strategy.GreedyPlacementStrategy._group_conflict_exists`) and by the post-hoc validator (`constraints/group_conflict.py`). This constraint only shapes the **group** view of the timetable — the teacher view always lists each teacher's activities individually, since teacher availability is validated separately by the teacher-conflict hard constraint.

## Soft constraints

Soft constraints are desirable preferences. Violations do not necessarily invalidate a proposal, but they reduce its score.

Examples of soft constraints:

- **Quarter-pair teacher match (highest priority)**: when a timeslot is validly shared by a `1Q`/`2Q` pair (see the hard constraint above), the proposal is scored much higher if both subjects are taught by the same teacher. Implemented in `ProposalScorer._quarter_pair_teacher_priority_score`, weighted well above every other soft component (`_QUARTER_PAIR_TEACHER_MATCH_WEIGHT`) so it wins the ranking among generated proposals whenever a same-teacher pairing is achievable without breaking a hard constraint.
- Preferred rooms: honoring a requirement's preferred room list.
- Preferred distribution: matching the documented preferred block shape.
- Teacher workload spread: avoiding too many consecutive hours for one teacher when possible.
- Group balance: distributing activities evenly across the week.
- Proposal compactness: avoiding isolated single-period fragments if alternatives exist.

## Scoring

A schedule proposal score is a floating-point value representing its quality.

- Higher scores indicate better proposals.
- The current v1 implementation uses a lightweight, deterministic score that is independent of proposal generation.
- The score is calculated by `ProposalScorer` from the proposal contents and the provided `GenerationContext`.

### Score composition

The current v1 formula is:

- `compactness_score`
- `+ distribution_score`
- `+ teacher_affinity_score`
- `+ quarter_pair_teacher_score` (highest-weighted soft component — see above)
- `- gap_penalty`
- `- warning_penalty`

This produces a simple `total_score` that rewards compact schedules and balanced distribution across allowed days while penalising warnings and fragmentation.

### Score components

- `compactness_score`: rewards proposals that keep activities concentrated in fewer days.
- `distribution_score`: rewards balanced use of the allowed days.
- `gap_penalty`: penalises gaps between activities in the same day based on their positions in the schedule.
- `warning_penalty`: penalises proposals with warnings.
- `metadata`: stores counts such as activity count and warning count for debugging and future expansion.

### Future extensibility

The scoring system remains intentionally modular and will grow incrementally.

- Teacher preferences, room preferences, and advanced optimisation are not implemented yet.
- Additional metrics can be added without changing the generator interface.
- A `ScoreBreakdown` object is attached to each `ScheduleProposal` for inspection and future ranking work.

## Penalties

Penalties are how the system differentiates bad proposals.

- Hard constraint penalty: large negative impact, typically enough to make the proposal worse than any valid alternative.
- Soft constraint penalty: moderate negative impact that allows the proposal to remain valid.
- Conflict penalty: each conflict reduces the score.
- Warning penalty: warnings reduce score less than conflicts but still discourage poor plans.

## Tie-breaking

When two proposals have the same score, tie-breaking should consider additional details such as:

- Fewer hard conflicts.
- Fewer warnings.
- More exact adherence to preferred room or distribution.
- Better workload distribution across teachers and days.
- Lower overall fragmentation of the schedule.

## Future extensibility

The scoring system should remain modular and extensible.

- Add new soft constraint rules without changing the core proposal representation.
- Keep scoring logic separate from schedule proposal generation and validation.
- Use `ScheduleProposal.metadata` to store intermediate scoring details.
- Support multiple ranking strategies, such as weighted scoring, lexicographic ranking, or scoring by rule category.
