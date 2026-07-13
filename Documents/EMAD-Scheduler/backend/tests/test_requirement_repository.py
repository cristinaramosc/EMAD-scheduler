from backend.repositories.requirement_repository import RequirementRepository
from backend.models.teaching_requirement import TeachingRequirement


def make_req(id=None):
    return TeachingRequirement(
        id=id,
        group_id="g1",
        subject_id="s1",
        teacher_id="t1",
        weekly_hours=2.0,
        min_days=1,
        max_days=2,
        min_block_duration=0.5,
        max_consecutive_hours=2.0,
        allow_half_hour_blocks=True,
    )


def test_create_and_get():
    repo = RequirementRepository()
    r = make_req()
    created = repo.create(r)
    assert created.id is not None
    fetched = repo.get(created.id)
    assert fetched is not None
    assert fetched.weekly_hours == r.weekly_hours


def test_list_and_delete():
    repo = RequirementRepository()
    r1 = repo.create(make_req())
    r2 = repo.create(make_req())
    lst = repo.list()
    assert len(lst) == 2
    assert repo.delete(r1.id) is True
    assert repo.get(r1.id) is None


def test_update():
    repo = RequirementRepository()
    created = repo.create(make_req())
    updated = repo.update(created.id, {"weekly_hours": 3.0})
    assert updated.weekly_hours == 3.0


def test_update_nonexistent():
    repo = RequirementRepository()
    assert repo.update("nope", {"weekly_hours": 1.0}) is None
