from fastapi import APIRouter

try:
    from ..database import SessionLocal
    from ..models.teacher import Teacher
    from ..models.activity import Activity
    from ..schemas.activity import ActivityUpdate
    from ..services.activity_service import update_activity
except ImportError:  # pragma: no cover
    from database import SessionLocal
    from models.teacher import Teacher
    from models.activity import Activity
    from schemas.activity import ActivityUpdate
    from services.activity_service import update_activity

router = APIRouter()


# -------------------------
# GET activitats professor
# -------------------------

@router.get("/activities")
def get_activities(teacher_id: int):

    db = SessionLocal()

    teacher = (
        db.query(Teacher)
        .filter(Teacher.id == teacher_id)
        .first()
    )

    if not teacher:
        db.close()
        return []

    activities = (
        db.query(Activity)
        .filter(Activity.teacher == teacher.name)
        .all()
    )

    resultat = []

    for a in activities:

        resultat.append(
            {
                "id": a.id,
                "subject": a.subject,
                "group": a.group_name,
                "room": a.room,
                "day": a.day,
                "start": a.start,
                "duration": a.duration,
            }
        )

    db.close()

    return resultat


# -------------------------
# PATCH activitat
# -------------------------

@router.patch("/activities/{activity_id}")
def patch_activity(activity_id: int, activity: ActivityUpdate):

    updated = update_activity(activity_id, activity)

    if updated is None:
        return {"ok": False}

    return {"ok": True}