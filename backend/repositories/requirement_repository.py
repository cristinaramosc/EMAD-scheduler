import copy
from typing import Dict, List, Optional
from uuid import uuid4

try:
    from backend.models.teaching_requirement import TeachingRequirement
except ModuleNotFoundError:  # pragma: no cover
    from models.teaching_requirement import TeachingRequirement


class RequirementRepository:
    """In-memory repository for TeachingRequirement.

    The repository stores TeachingRequirement instances keyed by id and
    exposes a simple CRUD API. No business logic here.
    """

    def __init__(self):
        self._store: Dict[str, TeachingRequirement] = {}

    def create(self, requirement: TeachingRequirement) -> TeachingRequirement:
        # ensure id as string UUID
        rid = requirement.id if requirement.id is not None else str(uuid4())
        if not isinstance(rid, str):
            rid = str(rid)
        # store a deepcopy to avoid accidental external mutation
        copy_req = copy.deepcopy(requirement)
        copy_req.id = rid
        self._store[rid] = copy_req
        return copy.deepcopy(copy_req)

    def get(self, requirement_id: str) -> Optional[TeachingRequirement]:
        req = self._store.get(str(requirement_id))
        return copy.deepcopy(req) if req is not None else None

    def list(self) -> List[TeachingRequirement]:
        return [copy.deepcopy(r) for r in self._store.values()]

    def update(self, requirement_id: str, data: Dict) -> Optional[TeachingRequirement]:
        key = str(requirement_id)
        if key not in self._store:
            return None

        existing = self._store[key]
        for k, v in data.items():
            if hasattr(existing, k):
                setattr(existing, k, v)

        # validate by triggering the model's validate
        existing.validate()

        return copy.deepcopy(existing)

    def delete(self, requirement_id: str) -> bool:
        return self._store.pop(str(requirement_id), None) is not None
