from typing import List, Dict

from fastapi import APIRouter, File, UploadFile

if __package__ and __package__.startswith("backend"):
    from backend.dependencies import get_live_schedule_use_cases
    from backend.schemas.scheduler import ManualActivityDTO, MoveDTO, ToggleGroupBreakDTO
else:  # pragma: no cover
    from dependencies import get_live_schedule_use_cases
    from schemas.scheduler import ManualActivityDTO, MoveDTO, ToggleGroupBreakDTO

router = APIRouter(prefix="/scheduler")


@router.post("/load")
def load(activities: List[Dict]):
    use_cases = get_live_schedule_use_cases()
    return use_cases.load(activities)


@router.post("/load-fet")
async def load_fet(file: UploadFile | None = File(None)):
    use_cases = get_live_schedule_use_cases()
    if file is None:
        return use_cases.load_fet()

    content = await file.read()
    return use_cases.load_fet(content)


@router.get("/state")
def state():
    use_cases = get_live_schedule_use_cases()
    return use_cases.state()


@router.post("/move")
def move(move_data: MoveDTO):
    use_cases = get_live_schedule_use_cases()
    return use_cases.move(move_data.activity_id, move_data.day, move_data.start)


@router.post("/activities")
def add_manual_activity(payload: ManualActivityDTO):
    use_cases = get_live_schedule_use_cases()
    return use_cases.add_manual_activity(
        subject=payload.subject,
        day=payload.day,
        start=payload.start,
        duration=payload.duration,
        teacher=payload.teacher,
        group=payload.group,
        room=payload.room,
    )


@router.delete("/activities/{activity_id}")
def delete_activity(activity_id: int):
    use_cases = get_live_schedule_use_cases()
    return use_cases.remove_activity(activity_id)


@router.post("/breaks/toggle")
def toggle_group_break(payload: ToggleGroupBreakDTO):
    use_cases = get_live_schedule_use_cases()
    return use_cases.toggle_group_break(payload.group, payload.day)


@router.post("/lunch-breaks/assign")
def assign_teacher_lunch_breaks():
    """Afegeix una hora de dinar (12h-16h) als professors amb classe matí i tarda."""
    use_cases = get_live_schedule_use_cases()
    return use_cases.assign_teacher_lunch_breaks()
