from typing import Dict, List, Optional

try:
    from backend.models.teaching_block import TeachingBlock
    from backend.models.teaching_requirement import TeachingRequirement
    from backend.repositories.requirement_repository import RequirementRepository
    from backend.services.block_generator import BlockGenerator
    from time_units import blocks_to_hours, hours_to_blocks
except ModuleNotFoundError:  # pragma: no cover
    from models.teaching_block import TeachingBlock
    from models.teaching_requirement import TeachingRequirement
    from repositories.requirement_repository import RequirementRepository
    from services.block_generator import BlockGenerator
    from time_units import blocks_to_hours, hours_to_blocks


class RequirementService:
    """Business logic for TeachingRequirement.

    All persistence operations go through the repository.
    """

    def __init__(self, repo: RequirementRepository):
        self.repo = repo

    def _normalize_hours_to_blocks_grid(self, payload: Dict) -> Dict:
        normalized = dict(payload)

        for field in ["weekly_hours", "min_block_duration", "max_consecutive_hours"]:
            if field in normalized and normalized[field] is not None:
                blocks = hours_to_blocks(float(normalized[field]))
                normalized[field] = blocks_to_hours(blocks)

        min_distribution_days = normalized.get("min_distribution_days", normalized.get("min_days", 1))
        max_distribution_days = normalized.get("max_distribution_days", normalized.get("max_days", 2))
        normalized["min_distribution_days"] = int(min_distribution_days)
        normalized["max_distribution_days"] = int(max_distribution_days)

        # Keep legacy aliases populated for backward compatibility.
        normalized["min_days"] = normalized["min_distribution_days"]
        normalized["max_days"] = normalized["max_distribution_days"]

        return normalized

    def create(self, payload: Dict) -> TeachingRequirement:
        normalized = self._normalize_hours_to_blocks_grid(payload)

        # normalize/validate payload and construct domain model
        # id can be provided or assigned by repository
        tr = TeachingRequirement(
            id=normalized.get("id"),
            group_id=str(normalized["group_id"]),
            subject_id=str(normalized["subject_id"]),
            teacher_id=str(normalized["teacher_id"]),
            weekly_hours=normalized["weekly_hours"],
            min_days=normalized["min_days"],
            max_days=normalized["max_days"],
            min_block_duration=normalized["min_block_duration"],
            max_consecutive_hours=normalized["max_consecutive_hours"],
            allow_half_hour_blocks=normalized.get("allow_half_hour_blocks", False),
            min_distribution_days=normalized.get("min_distribution_days"),
            max_distribution_days=normalized.get("max_distribution_days"),
            preferred_distribution=normalized.get("preferred_distribution", {}),
            preferred_rooms=normalized.get("preferred_rooms", []),
            fixed_teacher=normalized.get("fixed_teacher", False),
            priority=normalized.get("priority", 2),
        )

        # repository handles id assignment
        created = self.repo.create(tr)
        return created

    def get(self, requirement_id: str) -> Optional[TeachingRequirement]:
        return self.repo.get(requirement_id)

    def list(self) -> List[TeachingRequirement]:
        return self.repo.list()

    def update(self, requirement_id: str, data: Dict) -> TeachingRequirement:
        # validate fields before persisting
        # create a shallow merged dict and let repository/model validate
        existing = self.repo.get(requirement_id)
        if existing is None:
            raise KeyError("requirement_not_found")

        merged = existing.__dict__.copy()
        merged.update(data)
        merged = self._normalize_hours_to_blocks_grid(merged)

        # construct a temporay domain object to validate
        tmp = TeachingRequirement(
            id=merged.get("id"),
            group_id=str(merged["group_id"]),
            subject_id=str(merged["subject_id"]),
            teacher_id=str(merged["teacher_id"]),
            weekly_hours=merged["weekly_hours"],
            min_days=merged["min_days"],
            max_days=merged["max_days"],
            min_block_duration=merged["min_block_duration"],
            max_consecutive_hours=merged["max_consecutive_hours"],
            allow_half_hour_blocks=merged.get("allow_half_hour_blocks", False),
            min_distribution_days=merged.get("min_distribution_days"),
            max_distribution_days=merged.get("max_distribution_days"),
            preferred_distribution=merged.get("preferred_distribution", {}),
            preferred_rooms=merged.get("preferred_rooms", []),
            fixed_teacher=merged.get("fixed_teacher", False),
            priority=merged.get("priority", 2),
        )

        # if no exception raised, persist via repository
        updated = self.repo.update(requirement_id, merged)
        if updated is None:
            raise KeyError("requirement_not_found")

        return updated

    def delete(self, requirement_id: str) -> bool:
        return self.repo.delete(requirement_id)

    def generate_blocks(self, requirement_id: str) -> List[List[TeachingBlock]]:
        requirement = self.repo.get(requirement_id)
        if requirement is None:
            raise KeyError("requirement_not_found")

        generator = BlockGenerator()
        return generator.generate(requirement)
