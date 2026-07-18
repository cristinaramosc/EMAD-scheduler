from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Tuple


Record = Dict[str, Any]
Store = Dict[str, Dict[str, Any]]


@dataclass
class DatasetDelta:
    imported: int = 0
    created: int = 0
    updated: int = 0
    removed: int = 0
    removed_records: List[Record] = field(default_factory=list)


@dataclass
class AcademicImportReport:
    teachers: DatasetDelta
    groups: DatasetDelta
    subjects: DatasetDelta
    teaching_assignments: DatasetDelta
    rooms: DatasetDelta
    teacher_restrictions: DatasetDelta
    group_restrictions: DatasetDelta
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "teachers": _delta_to_dict(self.teachers),
            "groups": _delta_to_dict(self.groups),
            "subjects": _delta_to_dict(self.subjects),
            "teaching_assignments": _delta_to_dict(self.teaching_assignments),
            "rooms": _delta_to_dict(self.rooms),
            "teacher_restrictions": _delta_to_dict(self.teacher_restrictions),
            "group_restrictions": _delta_to_dict(self.group_restrictions),
            "warnings": list(self.warnings),
            "summary": {
                "teachers_imported": self.teachers.imported,
                "groups_imported": self.groups.imported,
                "subjects_imported": self.subjects.imported,
                "teaching_assignments": self.teaching_assignments.imported,
                "warnings": len(self.warnings),
            },
        }


def _delta_to_dict(delta: DatasetDelta) -> Dict[str, Any]:
    return {
        "imported": delta.imported,
        "created": delta.created,
        "updated": delta.updated,
        "removed": delta.removed,
        "removed_records": deepcopy(delta.removed_records),
    }


def _normalize_key(value: str) -> str:
    return value.strip().lower()


class AcademicDataRepository:
    def __init__(self) -> None:
        self._teachers: Store = {}
        self._groups: Store = {}
        self._subjects: Store = {}
        self._assignments: Store = {}
        self._rooms: Store = {}
        self._teacher_restrictions: Store = {}
        self._group_restrictions: Store = {}
        # canonical assignments represent weekly loads per assignment row
        self._canonical_assignments: Store = {}
        self._next_assignment_id = 1

        try:
            # lazy import to avoid cycles
            from backend.services.session_decomposer import SessionDecomposer

            self._decomposer = SessionDecomposer()
        except Exception:  # pragma: no cover
            from services.session_decomposer import SessionDecomposer

            self._decomposer = SessionDecomposer()

    def apply_snapshot(self, snapshot: Dict[str, List[Record]], warnings: Iterable[str] | None = None) -> AcademicImportReport:
        teachers = self._apply_dataset(
            self._teachers,
            snapshot.get("teachers", []),
            lambda record: _normalize_key(record["name"]),
        )
        groups = self._apply_dataset(
            self._groups,
            snapshot.get("groups", []),
            lambda record: _normalize_key(record["name"]),
        )
        subjects = self._apply_dataset(
            self._subjects,
            snapshot.get("subjects", []),
            lambda record: _normalize_key(record["name"]),
        )
        assignments = self._apply_teaching_assignments_dataset(snapshot.get("teaching_assignments", []))
        rooms = self._apply_dataset(
            self._rooms,
            snapshot.get("rooms", []),
            lambda record: _normalize_key(record["name"]),
        )
        teacher_restrictions = DatasetDelta()
        if "teacher_restrictions" in snapshot:
            teacher_restrictions = self._apply_dataset(
                self._teacher_restrictions,
                snapshot.get("teacher_restrictions", []),
                lambda record: _normalize_key(record["teacher"]),
            )
        group_restrictions = DatasetDelta()
        if "group_restrictions" in snapshot:
            group_restrictions = self._apply_dataset(
                self._group_restrictions,
                snapshot.get("group_restrictions", []),
                lambda record: _normalize_key(record["group"]),
            )

        return AcademicImportReport(
            teachers=teachers,
            groups=groups,
            subjects=subjects,
            teaching_assignments=assignments,
            rooms=rooms,
            teacher_restrictions=teacher_restrictions,
            group_restrictions=group_restrictions,
            warnings=list(warnings or []),
        )

    def summary(self) -> Dict[str, Any]:
        active_teachers = self._active_records(self._teachers)
        active_groups = self._active_records(self._groups)
        active_subjects = self._active_records(self._subjects)
        active_assignments = self._active_records(self._canonical_assignments)
        active_rooms = self._active_records(self._rooms)
        active_teacher_restrictions = self._active_records(self._teacher_restrictions)
        active_group_restrictions = self._active_records(self._group_restrictions)

        weekly_hours = round(
            sum(float(item.get("weekly_hours", 0.0)) for item in active_assignments),
            2,
        )

        return {
            "teachers": len(active_teachers),
            "groups": len(active_groups),
            "subjects": len(active_subjects),
            "teaching_assignments": len(active_assignments),
            "weekly_teaching_hours": weekly_hours,
            "rooms": len(active_rooms),
            "restrictions": len(active_teacher_restrictions) + len(active_group_restrictions),
            "teacher_restrictions": len(active_teacher_restrictions),
            "group_restrictions": len(active_group_restrictions),
        }

    def active_teaching_assignments(self) -> List[Record]:
        return self._active_records(self._assignments)

    def snapshot_for_generation(self) -> Dict[str, Any]:
        return {
            "teachers": self.list_teachers(),
            "groups": self.list_groups(),
            "subjects": self.list_subjects(),
            "assignments": self.active_canonical_assignments(),
            "teacher_restrictions": self.list_teacher_restrictions(),
            "group_restrictions": self.list_group_restrictions(),
        }

    def active_canonical_assignments(self) -> List[Record]:
        return self._active_records(self._canonical_assignments)

    def _generate_assignment_id(self) -> str:
        assignment_id = f"assignment-{self._next_assignment_id}"
        self._next_assignment_id += 1
        return assignment_id

    def create_canonical_assignment(self, record: Record) -> str:
        """Create a canonical teaching assignment row and rebuild sessions."""
        canonical_record = deepcopy(record)
        assignment_id = canonical_record.get("id") or self._generate_assignment_id()
        canonical_record["id"] = assignment_id
        self._canonical_assignments[assignment_id] = {"record": canonical_record, "active": True}
        self._rebuild_sessions_for_canonical(assignment_id)
        return assignment_id

    def update_canonical_assignment(self, assignment_id: str, record: Record) -> None:
        existing = self._canonical_assignments.get(assignment_id)
        if existing is None or not existing.get("active", False):
            raise KeyError("assignment_not_found")
        canonical_record = deepcopy(record)
        canonical_record["id"] = assignment_id
        existing["record"] = canonical_record
        existing["active"] = True
        self._rebuild_sessions_for_canonical(assignment_id)

    def create_or_update_canonical_assignment(self, record: Record) -> str:
        if record.get("id"):
            self.update_canonical_assignment(record["id"], record)
            return record["id"]

        subject = _normalize_key(record.get("subject", ""))
        group = _normalize_key(record.get("group", ""))
        matching_id = None
        for assignment_id, entry in self._canonical_assignments.items():
            active = entry.get("active", False)
            if not active:
                continue
            assignment = entry.get("record", {})
            if _normalize_key(assignment.get("subject", "")) == subject and _normalize_key(assignment.get("group", "")) == group:
                matching_id = assignment_id
                break

        if matching_id:
            self.update_canonical_assignment(matching_id, record)
            return matching_id

        return self.create_canonical_assignment(record)

    def duplicate_canonical_assignment(self, assignment_id: str) -> str:
        existing = self._canonical_assignments.get(assignment_id)
        if existing is None or not existing.get("active", False):
            raise KeyError("assignment_not_found")
        record = deepcopy(existing["record"])
        record.pop("id", None)
        return self.create_canonical_assignment(record)

    def delete_canonical_assignment(self, assignment_id: str) -> None:
        existing = self._canonical_assignments.get(assignment_id)
        if existing is None or not existing.get("active", False):
            return
        existing["active"] = False
        remove_keys = [k for k, v in self._assignments.items() if v.get("record", {}).get("canonical_key") == assignment_id and v.get("active", False)]
        for rk in remove_keys:
            self._assignments[rk]["active"] = False

    @staticmethod
    def _quarter_label(subject: str, quarter: str) -> str:
        text = (subject or "").strip()
        lower = text.lower()
        if lower.endswith("1q") or lower.endswith("2q"):
            return text
        return f"{text} {quarter}"

    def merge_quarter_assignments(self, first_id: str, second_id: str) -> str:
        """Compacta dues assignacions (normalment d'1 hora cadascuna, una
        pensada per al 1r trimestre i l'altra pel 2n) en una de sola de 2
        hores que comparteix la mateixa franja setmanal tot l'any, igual que
        'Foto 1Q + Anglès 2Q'. Es pot desfer amb split_merged_assignment."""
        first_entry = self._canonical_assignments.get(first_id)
        second_entry = self._canonical_assignments.get(second_id)
        if first_entry is None or not first_entry.get("active", False):
            raise KeyError("assignment_not_found")
        if second_entry is None or not second_entry.get("active", False):
            raise KeyError("assignment_not_found")

        first_record = deepcopy(first_entry["record"])
        second_record = deepcopy(second_entry["record"])

        if _normalize_key(first_record.get("group", "")) != _normalize_key(second_record.get("group", "")):
            raise ValueError("assignments_must_share_group")

        first_label = self._quarter_label(first_record.get("subject", ""), "1Q")
        second_label = self._quarter_label(second_record.get("subject", ""), "2Q")
        combined_subject = f"{first_label} + {second_label}"

        teachers = []
        for record in (first_record, second_record):
            for name in str(record.get("teacher", "")).split(","):
                name = name.strip()
                if name and name not in teachers:
                    teachers.append(name)

        combined_weekly_hours = float(first_record.get("weekly_hours") or 0) + float(second_record.get("weekly_hours") or 0)

        merged_record = {
            "teacher": ", ".join(teachers),
            "subject": combined_subject,
            "group": first_record.get("group", ""),
            "weekly_hours": combined_weekly_hours,
            "fixed_day": first_record.get("fixed_day") or second_record.get("fixed_day") or "",
            "fixed_start": first_record.get("fixed_start") or second_record.get("fixed_start") or "",
            "merged_from": [first_record, second_record],
        }

        self.delete_canonical_assignment(first_id)
        self.delete_canonical_assignment(second_id)

        return self.create_canonical_assignment(merged_record)

    def split_merged_assignment(self, assignment_id: str) -> List[str]:
        """Desfà una assignació compactada amb merge_quarter_assignments,
        recuperant les dues assignacions originals per separat."""
        entry = self._canonical_assignments.get(assignment_id)
        if entry is None or not entry.get("active", False):
            raise KeyError("assignment_not_found")

        record = entry["record"]
        merged_from = record.get("merged_from")
        if not merged_from or len(merged_from) != 2:
            raise ValueError("assignment_is_not_merged")

        self.delete_canonical_assignment(assignment_id)

        new_ids = []
        for original_record in merged_from:
            restored = deepcopy(original_record)
            restored.pop("id", None)
            new_ids.append(self.create_canonical_assignment(restored))
        return new_ids

    def _rebuild_sessions_for_canonical(self, canonical_key: str) -> None:
        entry = self._canonical_assignments.get(canonical_key)
        if entry is None or not entry.get("active", False):
            return
        record = entry.get("record")
        weekly = record.get("weekly_hours")
        allowed = record.get("allowed_session_lengths") or []
        max_session_days = record.get("max_session_days")
        try:
            if allowed:
                sessions = self._decomposer.decompose(float(weekly), allowed)
            elif max_session_days:
                sessions = self._decomposer.decompose_by_max_sessions(float(weekly), int(max_session_days))
            else:
                sessions = [float(weekly)]
        except Exception:
            sessions = [float(weekly)]

        for k, v in list(self._assignments.items()):
            if v.get("record", {}).get("canonical_key") == canonical_key and v.get("active", False):
                v["active"] = False

        for idx, session_length in enumerate(sessions, start=1):
            session_key = f"{canonical_key}|s{idx}"
            session_record = deepcopy(record)
            session_record["weekly_hours"] = session_length
            session_record["canonical_key"] = canonical_key
            session_record["session_index"] = idx
            existing = self._assignments.get(session_key)
            if existing is None:
                self._assignments[session_key] = {"record": session_record, "active": True}
            else:
                existing["record"] = session_record
                existing["active"] = True

    def active_subjects(self) -> List[Record]:
        return self._active_records(self._subjects)

    def active_teacher_restrictions(self) -> List[Record]:
        return self._active_records(self._teacher_restrictions)

    def active_group_restrictions(self) -> List[Record]:
        return self._active_records(self._group_restrictions)

    def _apply_teaching_assignments_dataset(self, incoming_records: List[Record]) -> DatasetDelta:
        delta = DatasetDelta(imported=len(incoming_records))
        previously_active = {key for key, value in self._canonical_assignments.items() if value.get("active", False)}
        incoming_by_key: Dict[str, Record] = {}

        for record in incoming_records:
            incoming_key = record.get("id") or "|".join(
                [
                    _normalize_key(record["teacher"]),
                    _normalize_key(record["subject"]),
                    _normalize_key(record["group"]),
                ]
            )
            incoming_by_key[incoming_key] = deepcopy(record)

        for key, incoming in incoming_by_key.items():
            existing = self._canonical_assignments.get(key)
            if existing is None:
                delta.created += 1
                canonical_id = incoming.get("id") or self._generate_assignment_id()
                incoming["id"] = canonical_id
                self._canonical_assignments[canonical_id] = {"record": incoming, "active": True}
                self._rebuild_sessions_for_canonical(canonical_id)
                continue

            changed = existing.get("record") != incoming or not existing.get("active", False)
            if changed:
                delta.updated += 1
                incoming["id"] = key
                existing["record"] = incoming
                existing["active"] = True
                self._rebuild_sessions_for_canonical(key)

        removed_keys = sorted(previously_active - set(incoming_by_key.keys()))
        for key in removed_keys:
            removed = self._canonical_assignments[key]
            removed["active"] = False
            delta.removed += 1
            delta.removed_records.append(deepcopy(removed["record"]))
            self.delete_canonical_assignment(key)

        return delta

    def list_teachers(self) -> List[Record]:
        return self._active_records(self._teachers)

    def create_teacher(self, record: Record) -> None:
        key = _normalize_key(record["name"])
        if self._teachers.get(key) and self._teachers[key].get("active", False):
            raise KeyError("teacher_already_exists")
        self._teachers[key] = {"record": deepcopy(record), "active": True}

    def update_teacher(self, old_name: str, record: Record) -> None:
        old_key = _normalize_key(old_name)
        existing = self._teachers.get(old_key)
        if existing is None or not existing.get("active", False):
            raise KeyError("teacher_not_found")
        new_key = _normalize_key(record["name"])
        if new_key != old_key and self._teachers.get(new_key) and self._teachers[new_key].get("active", False):
            raise KeyError("teacher_already_exists")
        self._teachers.pop(old_key)
        self._teachers[new_key] = {"record": deepcopy(record), "active": True}
        self._rename_teacher_references(old_name, record["name"])

    def delete_teacher(self, name: str) -> None:
        if any(a.get("record", {}).get("teacher") == name and a.get("active", False) for a in self._canonical_assignments.values()):
            raise ValueError("teacher_in_use")
        key = _normalize_key(name)
        existing = self._teachers.get(key)
        if existing:
            existing["active"] = False
        restriction_key = key
        if self._teacher_restrictions.get(restriction_key):
            self._teacher_restrictions[restriction_key]["active"] = False

    def _rename_teacher_references(self, old_name: str, new_name: str) -> None:
        for entry in self._canonical_assignments.values():
            record = entry.get("record")
            if record.get("teacher") == old_name:
                record["teacher"] = new_name
                self._rebuild_sessions_for_canonical(record["id"])
        old_key = _normalize_key(old_name)
        new_key = _normalize_key(new_name)
        restriction = self._teacher_restrictions.pop(old_key, None)
        if restriction and restriction.get("active", False):
            restriction["record"]["teacher"] = new_name
            self._teacher_restrictions[new_key] = restriction

    def list_groups(self) -> List[Record]:
        return self._active_records(self._groups)

    def create_group(self, record: Record) -> None:
        key = _normalize_key(record["name"])
        if self._groups.get(key) and self._groups[key].get("active", False):
            raise KeyError("group_already_exists")
        self._groups[key] = {"record": deepcopy(record), "active": True}

    def update_group(self, old_name: str, record: Record) -> None:
        old_key = _normalize_key(old_name)
        existing = self._groups.get(old_key)
        if existing is None or not existing.get("active", False):
            raise KeyError("group_not_found")
        new_key = _normalize_key(record["name"])
        if new_key != old_key and self._groups.get(new_key) and self._groups[new_key].get("active", False):
            raise KeyError("group_already_exists")
        self._groups.pop(old_key)
        self._groups[new_key] = {"record": deepcopy(record), "active": True}
        self._rename_group_references(old_name, record["name"])

    def delete_group(self, name: str) -> None:
        if any(a.get("record", {}).get("group") == name and a.get("active", False) for a in self._canonical_assignments.values()):
            raise ValueError("group_in_use")
        key = _normalize_key(name)
        existing = self._groups.get(key)
        if existing:
            existing["active"] = False
        restriction_key = key
        if self._group_restrictions.get(restriction_key):
            self._group_restrictions[restriction_key]["active"] = False

    def _rename_group_references(self, old_name: str, new_name: str) -> None:
        for entry in self._canonical_assignments.values():
            record = entry.get("record")
            if record.get("group") == old_name:
                record["group"] = new_name
                self._rebuild_sessions_for_canonical(record["id"])
        old_key = _normalize_key(old_name)
        new_key = _normalize_key(new_name)
        restriction = self._group_restrictions.pop(old_key, None)
        if restriction and restriction.get("active", False):
            restriction["record"]["group"] = new_name
            self._group_restrictions[new_key] = restriction

    def list_subjects(self) -> List[Record]:
        return self._active_records(self._subjects)

    def create_subject(self, record: Record) -> None:
        key = _normalize_key(record["name"])
        if self._subjects.get(key) and self._subjects[key].get("active", False):
            raise KeyError("subject_already_exists")
        self._subjects[key] = {"record": deepcopy(record), "active": True}

    def update_subject(self, old_name: str, record: Record) -> None:
        old_key = _normalize_key(old_name)
        existing = self._subjects.get(old_key)
        if existing is None or not existing.get("active", False):
            raise KeyError("subject_not_found")
        new_key = _normalize_key(record["name"])
        if new_key != old_key and self._subjects.get(new_key) and self._subjects[new_key].get("active", False):
            raise KeyError("subject_already_exists")
        self._subjects.pop(old_key)
        self._subjects[new_key] = {"record": deepcopy(record), "active": True}
        self._rename_subject_references(old_name, record["name"])
        if record.get("allowed_session_lengths") != existing["record"].get("allowed_session_lengths"):
            self._refresh_sessions_for_subject(record["name"])

    def delete_subject(self, name: str) -> None:
        if any(a.get("record", {}).get("subject") == name and a.get("active", False) for a in self._canonical_assignments.values()):
            raise ValueError("subject_in_use")
        key = _normalize_key(name)
        existing = self._subjects.get(key)
        if existing:
            existing["active"] = False

    def _rename_subject_references(self, old_name: str, new_name: str) -> None:
        for entry in self._canonical_assignments.values():
            record = entry.get("record")
            if record.get("subject") == old_name:
                record["subject"] = new_name
                self._rebuild_sessions_for_canonical(record["id"])

    def _refresh_sessions_for_subject(self, subject_name: str) -> None:
        for key, entry in self._canonical_assignments.items():
            record = entry.get("record")
            if record.get("subject") == subject_name and entry.get("active", False):
                self._rebuild_sessions_for_canonical(key)

    def list_rooms(self) -> List[Record]:
        return self._active_records(self._rooms)

    def create_room(self, record: Record) -> None:
        key = _normalize_key(record["name"])
        if self._rooms.get(key) and self._rooms[key].get("active", False):
            raise KeyError("room_already_exists")
        self._rooms[key] = {"record": deepcopy(record), "active": True}

    def update_room(self, old_name: str, record: Record) -> None:
        old_key = _normalize_key(old_name)
        existing = self._rooms.get(old_key)
        if existing is None or not existing.get("active", False):
            raise KeyError("room_not_found")
        new_key = _normalize_key(record["name"])
        if new_key != old_key and self._rooms.get(new_key) and self._rooms[new_key].get("active", False):
            raise KeyError("room_already_exists")
        self._rooms.pop(old_key)
        self._rooms[new_key] = {"record": deepcopy(record), "active": True}
        self._rename_room_references(old_name, record["name"])

    def delete_room(self, name: str) -> None:
        if any(a.get("record", {}).get("preferred_room") == name and a.get("active", False) for a in self._canonical_assignments.values()):
            raise ValueError("room_in_use")
        key = _normalize_key(name)
        existing = self._rooms.get(key)
        if existing:
            existing["active"] = False

    def _rename_room_references(self, old_name: str, new_name: str) -> None:
        for entry in self._canonical_assignments.values():
            record = entry.get("record")
            if record.get("preferred_room") == old_name:
                record["preferred_room"] = new_name
                self._rebuild_sessions_for_canonical(record["id"])

    def list_teacher_restrictions(self) -> List[Record]:
        return self._active_records(self._teacher_restrictions)

    def upsert_teacher_restriction(self, record: Record) -> None:
        key = _normalize_key(record["teacher"])
        self._teacher_restrictions[key] = {"record": deepcopy(record), "active": True}

    def delete_teacher_restriction(self, teacher: str) -> None:
        key = _normalize_key(teacher)
        existing = self._teacher_restrictions.get(key)
        if existing:
            existing["active"] = False

    def list_group_restrictions(self) -> List[Record]:
        return self._active_records(self._group_restrictions)

    def upsert_group_restriction(self, record: Record) -> None:
        key = _normalize_key(record["group"])
        self._group_restrictions[key] = {"record": deepcopy(record), "active": True}

    def delete_group_restriction(self, group: str) -> None:
        key = _normalize_key(group)
        existing = self._group_restrictions.get(key)
        if existing:
            existing["active"] = False

    def list_breaks(self) -> List[Record]:
        """Retorna els descansos/pauses horàries definits (p.ex. hora del pati),
        que el generador d'horaris ha de tractar com a franges bloquejades.
        Encara no hi ha una via per crear-ne des de la interfície, així que
        per defecte retorna una llista buida sense trencar la generació."""
        return [deepcopy(record) for record in getattr(self, "_breaks", [])]

    def set_breaks(self, records: List[Record]) -> None:
        self._breaks = [deepcopy(record) for record in records]

    def _active_records(self, store: Store) -> List[Record]:
        return [deepcopy(row["record"]) for row in store.values() if row.get("active", False)]

    def _apply_dataset(
        self,
        store: Store,
        incoming_records: List[Record],
        key_fn: Callable[[Record], str],
    ) -> DatasetDelta:
        delta = DatasetDelta(imported=len(incoming_records))

        previously_active = {key for key, value in store.items() if value.get("active", False)}
        incoming_by_key: Dict[str, Record] = {}

        for record in incoming_records:
            key = key_fn(record)
            incoming_by_key[key] = deepcopy(record)

        for key, incoming in incoming_by_key.items():
            existing = store.get(key)
            if existing is None:
                delta.created += 1
                store[key] = {"record": incoming, "active": True}
                continue

            changed = existing.get("record") != incoming or not existing.get("active", False)
            if changed:
                delta.updated += 1
                existing["record"] = incoming
                existing["active"] = True

        removed_keys = sorted(previously_active - set(incoming_by_key.keys()))
        for key in removed_keys:
            removed = store[key]
            removed["active"] = False
            delta.removed += 1
            delta.removed_records.append(deepcopy(removed["record"]))

        return delta
