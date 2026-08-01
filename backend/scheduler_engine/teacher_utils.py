from __future__ import annotations

from typing import Tuple


def teacher_names(value) -> Tuple[str, ...]:
    names = []

    def add(item) -> None:
        if item is None:
            return
        if isinstance(item, (list, tuple, set)):
            for nested in item:
                add(nested)
            return

        text = str(item).strip()
        if not text:
            return

        for part in text.split(","):
            candidate = part.strip()
            if candidate:
                names.append(candidate)

    add(value)

    unique = []
    seen = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)

    return tuple(unique)


def teacher_label(value) -> str:
    return ", ".join(teacher_names(value))