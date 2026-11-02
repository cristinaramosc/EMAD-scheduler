"""Escola fictícia per a les auditories de restriccions (sense dades reals ni cap Excel al projecte).

Conté els casos difícils: una professora que només ve dilluns, Projecte Integrat consecutiu
amb dos professors, una parella 1Q/2Q de durada diferent, una classe de grups combinats i
elsgrups de tarda amb els matins bloquejats."""
import io, openpyxl

DAYS = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
HALF_HOURS = [f"{h}:{m}" for h in range(8, 22) for m in ("00", "30")][:-1]  # 8:00 .. 21:00


def slots(days, start="8:00", end="21:00"):
    """Franges de mitja hora "Dia hora", des de `start` fins a `end` (inclosa)."""
    first, last = HALF_HOURS.index(start), HALF_HOURS.index(end)
    return ", ".join(f"{d} {h}" for d in days for h in HALF_HOURS[first:last + 1])


MORNINGS = slots(DAYS, "8:00", "14:30")          # grups de tarda: matins bloquejats
AFTERNOONS = slots(DAYS, "14:30", "21:00")       # grups de matí: tardes bloquejades

TEACHERS = [
    # nom, % dedicació, hores de centre, franges no disponibles
    ("Anna", 100, 7.5, slots(["Dimecres"])),
    ("Bernat", 100, 7.5, slots(["Dimarts"], "15:00", "21:00")),
    ("Carla", 35, 3.5, slots(DAYS[1:])),                       # només ve dilluns
    ("Dídac", 60, 5, ""),
    ("Elena", 100, 7.5, ""),
    ("Ferran", 80, 6, slots(["Divendres"], "8:00", "13:00")),
    ("Gemma", 100, 7.5, ""),
    ("Hugo", 100, 7.5, ""),
    ("Iris", 70, 5, slots(["Dijous"])),
    ("Joan", 100, 7.5, slots(["Dilluns"], "8:00", "12:00")),
]

# nom del grup, tutor, franges no disponibles, màx. dies
GROUPS = [
    ("1r DIS", "Anna", AFTERNOONS, ""),
    ("2n DIS", "Elena", slots(["Divendres"], "8:00", "10:00"), 4),
    ("Comú", "Dídac", MORNINGS, ""),
    ("GP", "Bernat", MORNINGS, ""),
    ("GI", "Hugo", MORNINGS, ""),
]

# assignatura, grup, professor/s, hores, durades permeses, aula, màx. dies, dia fix, hora fixa, consecutiva amb (assignatura, professor)
ASSIGNMENTS = [
    ("Dibuix", "1r DIS", "Anna", 4, "", "", "", "", "", "", ""),
    ("Color", "1r DIS", "Bernat", 3, "", "", "", "", "", "", ""),
    ("Història", "1r DIS", "Carla", 2, "", "", "", "Dilluns", "", "", ""),
    ("Anglès", "1r DIS", "Dídac", 2, "", "", "", "", "", "", ""),
    ("Taller", "1r DIS", "Elena", 6, "", "", "", "", "", "", ""),
    ("Projectes", "1r DIS", "Ferran", 3, "", "", "", "", "", "", ""),
    ("Tipografia", "2n DIS", "Anna", 3, "", "", "", "", "", "", ""),
    ("Web", "2n DIS", "Gemma", 4, "", "", "", "", "", "", ""),
    ("Fotografia", "2n DIS", "Hugo", 2, "", "", "", "", "", "", ""),
    ("Màrqueting", "2n DIS", "Iris", 2, "", "", "", "", "", "", ""),
    ("Taller", "2n DIS", "Elena", 5, "", "", "", "", "", "", ""),
    ("Projecte Integrat", "2n DIS", "Joan", 2, "", "", "", "", "", "Projecte Integrat", "Carla"),
    ("Projecte Integrat", "2n DIS", "Carla", 1, "", "", "", "", "", "Projecte Integrat", "Joan"),
    ("FOL", "Comú", "Carla", 2, "", "", "", "Dilluns", "", "", ""),
    ("Xerrades", "Comú", "Dídac", 2, "", "", "", "", "", "", ""),
    ("Estudi", "Comú", "Elena", 3, "", "", "", "", "", "", ""),
    ("Disseny", "GP", "Bernat", 4, "", "", "", "", "", "", ""),
    ("Tipografia GP", "GP", "Anna", 3, "", "", "", "", "", "", ""),
    ("Producció", "GP", "Gemma", 3, "", "", "", "", "", "", ""),
    ("Projecte Integrat", "GP", "Joan", 2, "", "", "", "", "", "Projecte Integrat", "Iris"),
    ("Projecte Integrat", "GP", "Iris", 1, "", "", "", "", "", "Projecte Integrat", "Joan"),
    ("Interfícies", "GI", "Gemma", 3, "", "", "", "", "", "", ""),
    ("Projecte Integrat", "GI", "Joan", 2, "", "", "", "", "", "Projecte Integrat", "Carla"),
    ("Projecte Integrat", "GI", "Carla", 1, "", "", "", "", "", "Projecte Integrat", "Joan"),
    ("Audio UF3 1Q", "GI", "Hugo", 4, "", "", "", "", "", "", ""),
    ("Audio UF3 2Q", "GI, GP", "Hugo", 3, "", "", "", "", "", "", ""),
    ("Foto UF3", "GI, GP", "Iris", 2, "", "", "", "", "", "", ""),
    ("Estudi GI", "GI", "Dídac", 2, "", "", "", "", "", "", ""),
]


def build_workbook(blank_bytes: bytes) -> bytes:
    """Omple la plantilla buida (mateixes capçaleres que fa servir l'aplicació)."""
    workbook = openpyxl.load_workbook(io.BytesIO(blank_bytes))
    professors, groups, assignments = workbook["Professors"], workbook["Grups"], workbook["Assignatures"]
    for name, pct, centre, blocked in TEACHERS:
        professors.append([name, "Sí", pct, "", centre, "", "", "No", None, None, None, blocked, ""])
    for name, tutor, blocked, max_days in GROUPS:
        groups.append([name, "Sí", tutor, "No", "No", None, None, max_days or None, None, "", blocked])
    for row in ASSIGNMENTS:
        assignments.append(list(row[:9]) + [row[9] or None, row[10] or None])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
