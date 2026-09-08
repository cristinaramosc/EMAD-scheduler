from typing import List, Dict

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

if __package__ and __package__.startswith("backend"):
    from backend.dependencies import get_live_schedule_use_cases
    from backend.schemas.scheduler import ManualActivityDTO, MoveDTO, ToggleGroupBreakDTO
    from backend.services.schedule_exporter import build_schedule_export
    from backend.services.schedule_pdf_exporter import build_schedule_pdf
else:  # pragma: no cover
    from dependencies import get_live_schedule_use_cases
    from schemas.scheduler import ManualActivityDTO, MoveDTO, ToggleGroupBreakDTO
    from services.schedule_exporter import build_schedule_export
    from services.schedule_pdf_exporter import build_schedule_pdf

router = APIRouter(prefix="/scheduler")


@router.post("/load")
def load(activities: List[Dict]):
    use_cases = get_live_schedule_use_cases()
    return use_cases.load(activities)


@router.get("/state")
def state():
    use_cases = get_live_schedule_use_cases()
    return use_cases.state()


@router.get("/export")
def export_schedule():
    """Descarrega un .xlsx amb una pestanya per a cada grup, professor i
    aula de l'horari actiu."""
    use_cases = get_live_schedule_use_cases()
    activities = use_cases.state().get("activities", [])
    buffer = build_schedule_export(activities)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=horaris.xlsx"},
    )


@router.get("/export/pdf")
def export_schedule_pdf():
    """Descarrega un .pdf amb una pàgina per a cada grup, professor i
    aula de l'horari actiu, amb un aspecte de calendari (graella per
    mitges hores i blocs blaus per a les activitats)."""
    use_cases = get_live_schedule_use_cases()
    activities = use_cases.state().get("activities", [])
    buffer = build_schedule_pdf(activities)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=horaris.pdf"},
    )


@router.get("/teacher/{teacher_name}/schedule")
def teacher_schedule(teacher_name: str):
    use_cases = get_live_schedule_use_cases()
    return use_cases.teacher_schedule(teacher_name)


@router.get("/room/{room_name}/schedule")
def room_schedule(room_name: str):
    use_cases = get_live_schedule_use_cases()
    return use_cases.room_schedule(room_name)


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


@router.post("/breaks/auto")
def auto_place_breaks():
    """Afegeix automàticament un descans a cada dia amb classes de cada
    grup que encara no en tingui cap."""
    use_cases = get_live_schedule_use_cases()
    return use_cases.auto_place_breaks()


@router.post("/lunch-breaks/assign")
def assign_teacher_lunch_breaks():
    """Afegeix una hora de dinar (12h-16h) als professors amb classe matí i tarda."""
    use_cases = get_live_schedule_use_cases()
    return use_cases.assign_teacher_lunch_breaks()


@router.post("/center-coordination-hours/assign")
def assign_center_and_coordination_hours():
    """Assigna el bloc fix de dimecres (Reunió 14-15h + Coordinació 15-16h)
    als professors que el tinguin activat, i reparteix la resta de les
    seves hores de centre/coordinació enganxades a les classes que ja
    tinguin."""
    use_cases = get_live_schedule_use_cases()
    return use_cases.assign_center_and_coordination_hours()
