import pytest

from backend.repositories.requirement_repository import RequirementRepository
from backend.services.requirement_service import RequirementService


def valid_payload():
    return {
        "group_id": "g1",
        "subject_id": "s1",
        "teacher_id": "t1",
        "weekly_hours": 2.0,
        "min_days": 1,
        "max_days": 2,
        "min_block_duration": 0.5,
        "max_consecutive_hours": 2.0,
        "allow_half_hour_blocks": True,
        "priority": 2,
    }


def test_create_and_list():
    repo = RequirementRepository()
    svc = RequirementService(repo)
    payload = valid_payload()
    created = svc.create(payload)
    assert created.id is not None
    all_req = svc.list()
    assert len(all_req) == 1


def test_update_flow():
    repo = RequirementRepository()
    svc = RequirementService(repo)
    payload = valid_payload()
    created = svc.create(payload)
    updated = svc.update(created.id, {"weekly_hours": 3.5})
    assert updated.weekly_hours == 3.5
    assert updated.weekly_blocks == 7


def test_delete_flow():
    repo = RequirementRepository()
    svc = RequirementService(repo)
    created = svc.create(valid_payload())
    assert svc.delete(created.id) is True


def test_validations_failures():
    repo = RequirementRepository()
    svc = RequirementService(repo)
    bad = valid_payload()
    bad["weekly_hours"] = 0
    with pytest.raises(ValueError):
        svc.create(bad)

    bad2 = valid_payload()
    bad2["min_days"] = 0
    with pytest.raises(ValueError):
        svc.create(bad2)

    bad3 = valid_payload()
    bad3["max_days"] = 0
    with pytest.raises(ValueError):
        svc.create(bad3)

    bad4 = valid_payload()
    bad4["min_block_duration"] = 0
    with pytest.raises(ValueError):
        svc.create(bad4)

    bad5 = valid_payload()
    bad5["max_consecutive_hours"] = 0
    with pytest.raises(ValueError):
        svc.create(bad5)

    bad6 = valid_payload()
    bad6["priority"] = 5
    with pytest.raises(ValueError):
        svc.create(bad6)


def test_generate_blocks_from_requirement():
    repo = RequirementRepository()
    svc = RequirementService(repo)
    payload = valid_payload()
    payload["weekly_hours"] = 4.0
    payload["min_days"] = 1
    payload["max_days"] = 2
    payload["min_block_duration"] = 1.0
    payload["max_consecutive_hours"] = 4.0
    payload["allow_half_hour_blocks"] = False
    created = svc.create(payload)

    blocks = svc.generate_blocks(created.id)
    assert len(blocks) >= 2
    assert [[block.duration for block in dist] for dist in blocks][:2] == [[4.0], [1.0, 3.0]]


def test_legacy_distribution_fields_remain_supported():
    repo = RequirementRepository()
    svc = RequirementService(repo)
    created = svc.create(valid_payload())

    assert created.min_distribution_days == 1
    assert created.max_distribution_days == 2
    assert created.min_days == 1
    assert created.max_days == 2


def test_generate_blocks_not_found():
    repo = RequirementRepository()
    svc = RequirementService(repo)
    with pytest.raises(KeyError):
        svc.generate_blocks("missing")
