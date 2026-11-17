from __future__ import annotations

from functools import lru_cache
from typing import Tuple


@lru_cache(maxsize=2048)
def _teacher_names_for_text(value: str) -> Tuple[str, ...]:
    unique = []
    seen = set()
    for part in value.split(","):
        candidate = part.strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return tuple(unique)


def teacher_names(value) -> Tuple[str, ...]:
    if isinstance(value, str):
        return _teacher_names_for_text(value.strip())

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