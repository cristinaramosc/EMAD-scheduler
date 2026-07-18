try:
    from ..database import SessionLocal
    from ..models.teacher import Teacher
except ImportError:  # pragma: no cover
    from database import SessionLocal
    from models.teacher import Teacher


def get_all_teachers():

    db = SessionLocal()

    teachers = (
        db.query(Teacher)
        .order_by(Teacher.name)
        .all()
    )

    resultat = [
        {
            "id": t.id,
            "name": t.name,
        }
        for t in teachers
    ]

    db.close()

    return resultat