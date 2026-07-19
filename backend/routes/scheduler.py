from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if __package__ and __package__.startswith("backend"):
    from backend.dependencies import get_proposal_store, get_scheduler_use_cases
    from backend.schemas.scheduler import MoveDTO, SwapDTO
else:  # pragma: no cover
    from dependencies import get_proposal_store, get_scheduler_use_cases
    from schemas.scheduler import MoveDTO, SwapDTO

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])
proposal_store = get_proposal_store()


class ActivityDto(BaseModel):
    id: int
    teacher: str
    subject: str
    group: str
    room: str
    day: str
    start: str
    duration: int


class GenerateRequest(BaseModel):
    requirement_ids: List[str]


@router.post("/validate")
def validate(activities: list[ActivityDto]):
    use_cases = get_scheduler_use_cases()
    return use_cases.validate([activity.dict() for activity in activities])


@router.post("/generate")
def generate_proposals(payload: GenerateRequest):
    use_cases = get_scheduler_use_cases()
    try:
        return use_cases.generate_proposals(payload.requirement_ids)
    except ValueError:
        raise HTTPException(status_code=400, detail="At least one teaching requirement is required")
    except LookupError:
        raise HTTPException(status_code=404, detail="No teaching requirements were found")
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Scheduling generation produced no proposals")
    except Exception as exc:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Scheduling generation failed: {exc}") from exc


@router.post("/proposal/{proposal_id}/accept")
def accept_proposal(proposal_id: str):
    use_cases = get_scheduler_use_cases()
    try:
        return use_cases.accept_proposal(proposal_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal_not_found")


@router.post("/proposal/{proposal_id}/move")
def move_proposal_activity(proposal_id: str, move_data: MoveDTO):
    use_cases = get_scheduler_use_cases()
    try:
        return use_cases.move_proposal_activity(
            proposal_id,
            move_data.activity_id,
            move_data.day,
            move_data.start,
        )
    except LookupError as exc:
        detail = "proposal_not_found" if str(exc) == "proposal_not_found" else "proposal_activity_not_found"
        raise HTTPException(status_code=404, detail=detail)


@router.post("/proposal/{proposal_id}/swap")
def swap_proposal_activities(proposal_id: str, swap_data: SwapDTO):
    use_cases = get_scheduler_use_cases()
    try:
        return use_cases.swap_proposal_activities(
            proposal_id,
            swap_data.activity_id_a,
            swap_data.activity_id_b,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal_not_found")


@router.post("/proposal/{proposal_id}/undo")
def undo_proposal_move(proposal_id: str):
    use_cases = get_scheduler_use_cases()
    try:
        return use_cases.undo_last_move(proposal_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal_not_found")


@router.get("/proposal/{proposal_id}/activity/{activity_id}/suggestions")
def suggest_slots_for_unscheduled(proposal_id: str, activity_id: int):
    use_cases = get_scheduler_use_cases()
    try:
        return use_cases.suggest_slots_for_unscheduled(proposal_id, activity_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal_not_found")


@router.post("/compact")
def compact_active_schedule():
    """Elimina els forats (franges buides) de l'horari actiu, reubicant les
    activitats de cada grup el més aviat possible dins de cada dia."""
    use_cases = get_scheduler_use_cases()
    return use_cases.compact_active_schedule()


@router.post("/proposal/{proposal_id}/compact")
def compact_proposal(proposal_id: str):
    """Elimina els forats d'una proposta generada."""
    use_cases = get_scheduler_use_cases()
    try:
        return use_cases.compact_proposal(proposal_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal_not_found")

