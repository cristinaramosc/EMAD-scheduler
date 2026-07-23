from backend.database import SessionLocal
from backend.models.activity import Activity
from backend.models.teacher import Teacher

from backend.services.fet_importer import load_activities

db = SessionLocal()

# Esborrem dades antigues
db.query(Activity).delete()
db.query(Teacher).delete()

activities = load_activities("../EMAD_2627_.fet")

teacher_names = set()

for a in activities:
    # Millora: suport per múltiples professors
    if a.get("teachers"):                    # nova llista
        for teacher_name in a["teachers"]:
            if teacher_name:
                teacher_names.add(teacher_name)
    elif a.get("teacher"):                   # compatibilitat antiga
        if a["teacher"]:
            teacher_names.add(a["teacher"])

    db.add(
        Activity(
            fet_id=a["fet_id"],
            teacher=a.get("teacher") or "",   # mantenim el camp actual
            subject=a["subject"],
            group_name=a["group_name"],
            duration=a["duration"],
            day=a["day"],
            start=a["start"],
            room=a["room"],
        )
    )

# Creem els professors únics
for name in sorted(teacher_names):
    db.add(Teacher(name=name))

db.commit()

print(f"{len(teacher_names)} professors importats.")
print(f"{len(activities)} activitats importades.")

db.close()