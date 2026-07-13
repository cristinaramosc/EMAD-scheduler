from typing import List
from uuid import uuid4

try:
    from backend.models.teaching_block import TeachingBlock
    from backend.models.teaching_requirement import TeachingRequirement
    from time_units import blocks_to_hours
except ModuleNotFoundError:  # pragma: no cover
    from models.teaching_block import TeachingBlock
    from models.teaching_requirement import TeachingRequirement
    from time_units import blocks_to_hours


def _generate_block_distributions(requirement: TeachingRequirement) -> List[List[int]]:
    total_blocks = requirement.weekly_blocks
    min_block_size = requirement.min_block_duration_blocks
    max_block_size = requirement.max_consecutive_blocks
    min_distribution_days = requirement.min_distribution_days
    max_distribution_days = requirement.max_distribution_days

    distributions: List[List[int]] = []

    def build_for_days(prefix: List[int], remaining: int, days_left: int) -> None:
        if days_left == 0:
            if remaining == 0:
                distributions.append(prefix.copy())
            return

        min_possible = min_block_size * days_left
        max_possible = max_block_size * days_left
        if remaining < min_possible or remaining > max_possible:
            return

        for block_count in range(min_block_size, min(max_block_size, remaining) + 1):
            prefix.append(block_count)
            build_for_days(prefix, remaining - block_count, days_left - 1)
            prefix.pop()

    for days in range(min_distribution_days, max_distribution_days + 1):
        build_for_days([], total_blocks, days)

    unique: List[List[int]] = []
    seen = set()
    for distribution in distributions:
        if len(distribution) < min_distribution_days or len(distribution) > max_distribution_days:
            continue
        if any(size < min_block_size or size > max_block_size for size in distribution):
            continue
        if sum(distribution) != total_blocks:
            continue
        if tuple(distribution) not in seen:
            seen.add(tuple(distribution))
            unique.append(distribution)

    unique.sort(key=lambda dist: (len(dist), dist))
    return unique


def generate_distributions(requirement: TeachingRequirement) -> List[List[float]]:
    distributions = _generate_block_distributions(requirement)
    return [[blocks_to_hours(value) for value in distribution] for distribution in distributions]


def generate_block_distributions(requirement: TeachingRequirement) -> List[List[int]]:
    return _generate_block_distributions(requirement)


class BlockGenerator:
    """Genera distribucions de TeachingBlocks per a un TeachingRequirement."""

    def generate(self, requirement: TeachingRequirement) -> List[List[TeachingBlock]]:
        block_distributions = generate_block_distributions(requirement)
        result: List[List[TeachingBlock]] = []

        for distribution in block_distributions:
            blocks = [
                TeachingBlock(
                    id=str(uuid4()),
                    duration=blocks_to_hours(block_count),
                    duration_blocks=block_count,
                    order=index + 1,
                )
                for index, block_count in enumerate(distribution)
            ]
            result.append(blocks)

        return result
