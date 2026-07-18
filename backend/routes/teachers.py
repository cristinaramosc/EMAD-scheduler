from fastapi import APIRouter

try:
    from ..services.teacher_service import get_all_teachers
except ImportError:  # pragma: no cover
    from services.teacher_service import get_all_teachers

router = APIRouter()


@router.get("/teachers")
def teachers():
    return get_all_teachers()