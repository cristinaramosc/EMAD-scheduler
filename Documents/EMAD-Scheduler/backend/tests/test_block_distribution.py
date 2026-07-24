"""Unit tests for two related block-generation fixes:

1. SchedulerGenerator must use a single distribution per teaching
   requirement, not flatten every valid distribution (which used to
   duplicate the weekly hours, e.g. 1h showing up as 4 slots instead of 2).
2. No generated teaching block may be shorter than 1 hour (2 half-hour
   blocks), even if the academic data configures a shorter min_block_duration.
"""

from backend.models.teaching_requirement import TeachingRequirement
from backend.scheduler_engine.generator import SchedulerGenerator
from backend.services.block_generator import BlockGenerator


def _requirement(**overrides) -> TeachingRequirement:
    defaults = dict(
        id="req-1",
        group_id="2A",
        subject_id="Projecte Integrat",
        teacher_id="eli",
        weekly_hours=1.0,
        min_days=1,
        max_days=1,
        min_block_duration=0.5,
        max_consecutive_hours=1.0,
        allow_half_hour_blocks=True,
    )
    defaults.update(overrides)
    return TeachingRequirement(**defaults)


def test_block_generator_never_yields_half_hour_chunks():
    """Even with min_block_duration=0.5h in the academic data, no single
    teaching chunk should ever be shorter than 1 hour (2 blocks)."""
    requirement = _requirement(
        weekly_hours=1.5,
        min_days=1,
        max_days=2,
        min_block_duration=0.5,
        max_consecutive_hours=1.5,
    )

    distributions = BlockGenerator().generate(requirement)

    assert distributions, "hi hauria d'haver almenys una distribució vàlida"
    for distribution in distributions:
        for block in distribution:
            assert block.duration_blocks >= 2, (
                f"bloc de {block.duration_blocks} franges (< 1h) no hauria d'existir"
            )


def test_generated_blocks_total_exactly_one_hour_not_more():
    """Reproduces the reported case: 'Projecte Integrat' is 1h/week total
    (2 blocks). The generated teaching blocks must sum to exactly 2 blocks,
    never 4."""
    requirement = _requirement(weekly_hours=1.0, min_days=1, max_days=1)

    generator = SchedulerGenerator()
    blocks = generator._build_blocks_from_requirements([requirement])

    assert sum(block.duration_blocks for block in blocks) == requirement.weekly_blocks
    assert sum(block.duration_blocks for block in blocks) == 2
    assert all(block.duration_blocks >= 2 for block in blocks)


def test_build_blocks_from_requirements_uses_a_single_distribution():
    """Reproduces the duplication bug: a requirement whose weekly hours can
    be validly split in more than one way (e.g. one 4-block day, or two
    2-block days) must only contribute ONE of those distributions, not the
    sum of all of them."""
    requirement = _requirement(
        subject_id="Multimedia",
        teacher_id="sonia",
        weekly_hours=2.0,
        min_days=1,
        max_days=2,
        min_block_duration=0.5,
        max_consecutive_hours=2.0,
    )

    # Sanity check on the fixture: there must be more than one valid way to
    # distribute these hours, otherwise this test wouldn't exercise the bug.
    distributions = BlockGenerator().generate(requirement)
    assert len(distributions) > 1

    generator = SchedulerGenerator()
    blocks = generator._build_blocks_from_requirements([requirement])
    total_blocks = sum(block.duration_blocks for block in blocks)

    # Before the fix this would be 8 (every distribution's blocks summed).
    assert total_blocks == requirement.weekly_blocks
    assert total_blocks == 4


def test_multiple_requirements_are_each_reduced_to_one_distribution():
    """Two requirements in the same call should each contribute only their
    own single distribution, with no cross-contamination or duplication."""
    req_a = _requirement(id="req-a", subject_id="Projecte Integrat", weekly_hours=1.0, min_days=1, max_days=1)
    req_b = _requirement(
        id="req-b",
        subject_id="Multimedia",
        teacher_id="sonia",
        weekly_hours=2.0,
        min_days=1,
        max_days=2,
        max_consecutive_hours=2.0,
    )

    generator = SchedulerGenerator()
    blocks = generator._build_blocks_from_requirements([req_a, req_b])

    blocks_a = [b for b in blocks if b.metadata.get("requirement_id") == "req-a"]
    blocks_b = [b for b in blocks if b.metadata.get("requirement_id") == "req-b"]

    assert sum(b.duration_blocks for b in blocks_a) == req_a.weekly_blocks
    assert sum(b.duration_blocks for b in blocks_b) == req_b.weekly_blocks
