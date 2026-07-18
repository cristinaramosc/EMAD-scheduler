import pytest

from backend.models.teaching_requirement import TeachingRequirement
from backend.services.block_generator import BlockGenerator


def make_requirement(weekly_hours, min_days, max_days, min_block_duration, max_consecutive_hours, allow_half_hour_blocks):
    return TeachingRequirement(
        id="req-1",
        group_id="g1",
        subject_id="s1",
        teacher_id="t1",
        weekly_hours=weekly_hours,
        min_days=min_days,
        max_days=max_days,
        min_block_duration=min_block_duration,
        max_consecutive_hours=max_consecutive_hours,
        allow_half_hour_blocks=allow_half_hour_blocks,
    )


@pytest.mark.parametrize(
    "req",
    [
        make_requirement(4.0, 1, 4, 0.5, 4.0, True),
        make_requirement(5.0, 2, 3, 1.0, 3.0, False),
        make_requirement(6.0, 1, 3, 0.5, 4.0, True),
        make_requirement(7.0, 2, 4, 0.5, 4.0, True),
        make_requirement(8.0, 2, 4, 1.0, 4.0, False),
        make_requirement(9.0, 2, 5, 0.5, 5.0, True),
    ],
)
def test_block_generator_respects_time_grid_and_distribution_constraints(req):
    generator = BlockGenerator()
    result = generator.generate(req)

    for distribution in result:
        assert req.min_distribution_days <= len(distribution) <= req.max_distribution_days
        assert sum(block.duration for block in distribution) == pytest.approx(req.weekly_hours)

        for block in distribution:
            assert block.duration_blocks is not None
            assert block.duration_blocks >= req.min_block_duration_blocks
            assert block.duration_blocks <= req.max_consecutive_blocks
            # 1 block = 0.5h
            assert block.duration == pytest.approx(block.duration_blocks * 0.5)


def test_block_generator_returns_empty_when_constraints_are_impossible():
    req = make_requirement(
        weekly_hours=5.0,
        min_days=3,
        max_days=3,
        min_block_duration=2.0,
        max_consecutive_hours=2.0,
        allow_half_hour_blocks=True,
    )

    generator = BlockGenerator()
    result = generator.generate(req)

    assert result == []


def test_block_generator_no_duplicates():
    req = make_requirement(5.0, 1, 3, 0.5, 3.0, True)
    generator = BlockGenerator()
    result = generator.generate(req)
    durations = [[block.duration for block in dist] for dist in result]
    assert len(durations) == len(set(tuple(d) for d in durations))


def test_block_generator_deterministic_order():
    req = make_requirement(4.0, 1, 4, 0.5, 4.0, True)
    generator = BlockGenerator()
    first = generator.generate(req)
    second = generator.generate(req)
    assert [ [block.duration for block in dist] for dist in first ] == [ [block.duration for block in dist] for dist in second ]
