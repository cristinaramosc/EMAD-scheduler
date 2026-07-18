import xml.etree.ElementTree as ET

from backend.database import SessionLocal
from backend.models.teacher import Teacher

FET_FILE = "../EMAD_2627_.fet"


def import_teachers():
    tree = ET.parse(FET_FILE)
    root = tree.getroot()

    teachers_list = root.find("Teachers_List")

    if teachers_list is None:
        print("No s'ha trobat Teachers_List")
        return

    db = SessionLocal()

    count = 0

    for teacher in teachers_list.findall("Teacher"):
        name = teacher.findtext("Name")

        if not name:
            continue

        existeix = db.query(Teacher).filter_by(name=name).first()

        if existeix:
            continue

        db.add(Teacher(name=name))
        count += 1

    db.commit()
    db.close()

    print(f"{count} professors importats.")


if __name__ == "__main__":
    import_teachers()