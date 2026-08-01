"""Construeix el GenerationContext (i la llista de TeachingRequirement)
a partir de la base de dades, en substitució de `fet_importer.load_generation_inputs`.

AJUSTA els noms de model/camp de la secció "Suposicions" al teu esquema
real (SQLAlchemy). La resta (construcció del GenerationContext, gestió
del quadrimestre) ja hauria de ser correcta tal qual, perquè es basa
només en el contracte de TeachingRequirement/GenerationContext que ja
existeix al motor.
"""

from __future__ import annotations

from typing import List

try:
    from backend.scheduler_engine.models import GenerationContext, SchoolCalendar, TeachingRequirement
    from backend.scheduler_engine.quarter_utils import with_quarter_suffix
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.models import GenerationContext, SchoolCalendar, TeachingRequirement
    from scheduler_engine.quarter_utils import with_quarter_suffix

# --- Suposicions: ajusta als teus models reals -----------------------------
# from backend.models.group import Group
# from backend.models.subject import Subject
# from backend.models.teaching_requirement import TeachingRequirementDB
# from backend.models.school_config import SchoolConfig
# ---------------------------------------------------------------------------


def build_teaching_requirements(db) -> List[TeachingRequirement]:
    """Llegeix els requeriments docents de la BD i els converteix al model
    de domini TeachingRequirement, resolent l'etiqueta d'assignatura amb
    el sufix 1Q/2Q quan calgui.

    Suposa que cada fila de requeriment té una relació a Subject amb un
    camp `name` (net, sense sufix) i un camp `quarter` amb valors
    None / "1Q" / "2Q".
    """
    requirements: List[TeachingRequirement] = []

    # db_requirements = db.query(TeachingRequirementDB).all()  # <-- ajusta
    db_requirements = []  # placeholder

    for row in db_requirements:
        subject_label = with_quarter_suffix(row.subject.name, row.subject.quarter)

        requirements.append(
            TeachingRequirement(
                id=str(row.id),
                group_id=row.group.name,  # nom net del grup genèric, p.ex. "1r APGI"
                subject_id=subject_label,  # etiqueta amb sufix perquè el motor detecti parelles 1Q/2Q
                teacher_id=row.teacher.name,
                weekly_hours=row.weekly_hours,
                min_days=row.min_days,
                max_days=row.max_days,
                min_block_duration=row.min_block_duration,
                max_consecutive_hours=row.max_consecutive_hours,
                allow_half_hour_blocks=row.allow_half_hour_blocks,
                preferred_rooms=[r.name for r in row.preferred_rooms] if row.preferred_rooms else [],
                fixed_day=row.fixed_day,
                fixed_start=row.fixed_start,
                priority=row.priority or 2,
            )
        )

    return requirements


def build_generation_context(db) -> GenerationContext:
    """Substitueix `fet_importer.load_generation_inputs`: construeix el
    GenerationContext llegint el calendari i les restriccions de la BD
    en lloc del XML de FET."""

    # school_config = db.query(SchoolConfig).first()  # <-- ajusta
    # school_calendar = SchoolCalendar(
    #     days=list(range(school_config.number_of_days)),
    #     periods_per_day=school_config.number_of_hours,
    # )
    school_calendar = SchoolCalendar(days=list(range(5)), periods_per_day=8)  # placeholder

    return GenerationContext(
        school_calendar=school_calendar,
        existing_scheduled_activities=(),
        fixed_activities=(),
        blocked_time_slots=(),
        configuration={
            # "split_groups": ...,               # grups desdoblats, si en teniu
            # "group_time_window_constraints": ...,
            # "hour_names": ...,
            # "room_constraints_enabled": True,
        },
    )
