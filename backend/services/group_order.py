"""Ordre fix dels grups a les exportacions (PDF i Excel).

És el mateix que fa servir el frontend a les pestanyes de grup. Els grups que
no hi són (p.ex. un de nou) van al final, per ordre alfabètic."""

from __future__ import annotations

from typing import Tuple

GROUP_ORDER = ["PFI", "1r COM", "2n COM", "1r APGI", "2n APGI", "Comú", "GP", "GI"]
_INDEX = {name.casefold(): position for position, name in enumerate(GROUP_ORDER)}


def group_sort_key(name: str) -> Tuple[int, str]:
    text = str(name or "").strip()
    return (_INDEX.get(text.casefold(), len(GROUP_ORDER)), text.casefold())
