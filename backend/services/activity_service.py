try:
    from ..database import SessionLocal
    from ..models.activity import Activity
except ImportError:  # pragma: no cover
    from database import SessionLocal
    from models.activity import Activity


def update_activity(activity_id: int, data):

    db = SessionLocal()

    activity = db.query(Activity).filter(
        Activity.id == activity_id
    ).first()

    if activity is None:
        db.close()
        return None

    activity.day = data.day
    activity.start = data.start
    activity.room = data.room

    db.commit()
    db.refresh(activity)

    db.close()

    return activity