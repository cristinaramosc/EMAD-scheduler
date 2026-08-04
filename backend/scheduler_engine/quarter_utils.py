"""Utilitats compartides per al concepte de quadrimestre (1Q/2Q).

Aquest mòdul substitueix la lògica que abans vivia només dins
`constraints/group_conflict.py`, perquè ara també la necessita el CRUD
(per construir l'etiqueta d'assignatura que arriba al motor) i qualsevol
altre punt que hagi de saber si un grup/assignatura pertany a un
quadrimestre concret.

Col·loca aquest fitxer a `backend/scheduler_engine/quarter_utils.py`
(o on tingueu la resta d'utilitats de domini) i actualitza els imports
a `group_conflict.py` per apuntar-hi, en lloc de mantenir una còpia.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

_QUARTER_1Q = "1q"
_QUARTER_2Q = "2q"


def quarter_suffix(text: Optional[str]) -> Optional[str]:
    """Retorna '1q' o '2q' si el text acaba amb aquest sufix (independent
    de majúscules/minúscules i espais), o None en cas contrari."""
    value = (text or "").strip().lower()
    if value.endswith(_QUARTER_1Q):
        return _QUARTER_1Q
    if value.endswith(_QUARTER_2Q):
        return _QUARTER_2Q
    return None


def strip_quarter_suffix(text: Optional[str]) -> str:
    """Retorna el text sense el sufix 1Q/2Q (si en té), amb espais nets."""
    value = (text or "").strip()
    suffix = quarter_suffix(value)
    if suffix is None:
        return value
    return value[: -len(suffix)].strip()


def subject_base_name(text: Optional[str]) -> str:
    """Retorna el nom base d'assignatura, sense sufix 1Q/2Q, normalitzat.

    Es fa servir per assegurar que una compartició 1Q/2Q només sigui
    possible quan ambdues activitats corresponen a la mateixa assignatura
    (mateix nom base), i no a matèries diferents del mateix grup pare.
    """
    base = strip_quarter_suffix(text)
    return re.sub(r"\s+", " ", base).strip().casefold()


def normalize_group_name(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def with_quarter_suffix(base_name: str, quarter: Optional[str]) -> str:
    """Construeix l'etiqueta d'assignatura que ha de veure el motor de
    col·locació, a partir del nom net (vingui del CRUD, amb el seu ID
    propi) i el periode ('1Q', '2Q' o None per anual).

    Fes servir això quan construeixis el `metadata["subject"]` que
    s'envia al TeachingBlock/ScheduledActivity, perquè el motor pugui
    seguir detectant parelles 1Q/2Q pel sufix del text sense necessitat
    que `subject_id` deixi de ser un identificador net.
    """
    base = (base_name or "").strip()
    if not quarter:
        return base
    normalized = quarter.strip().upper()
    if normalized not in {"1Q", "2Q"}:
        raise ValueError("quarter must be '1Q', '2Q' or falsy for anual")
    return f"{base} {normalized}"


def parent_and_quarter(group: Optional[str], subject: Optional[str]) -> Tuple[str, Optional[str]]:
    """Retorna (grup_pare, marcador_de_quadrimestre) per a una combinació
    de grup + assignatura. El marcador es dedueix primer del nom del grup
    (compatibilitat amb dades antigues on encara porti el sufix); si el
    grup no en té, es dedueix del nom de l'assignatura — que és el cas
    esperat per a dades noves creades pel CRUD."""
    group_text = (group or "").strip()
    group_quarter = quarter_suffix(group_text)
    if group_quarter is not None:
        return normalize_group_name(strip_quarter_suffix(group_text)), group_quarter

    return normalize_group_name(group_text), quarter_suffix(subject)


def is_valid_quarter_pair(
    first_group: Optional[str],
    first_subject: Optional[str],
    second_group: Optional[str],
    second_subject: Optional[str],
) -> bool:
    """Dues activitats del mateix grup pare poden coexistir a la mateixa
    franja horària si comparteixen grup pare i una és 1Q i l'altra 2Q —
    poden ser assignatures completament diferents (p.ex. 'FOL 1Q' i
    'Anglès 2Q'), ja que en aquest grup no hi ha mai classe simultània de
    1Q i 2Q: només compten com la mateixa franja del grup.
    """
    parent_a, quarter_a = parent_and_quarter(first_group, first_subject)
    parent_b, quarter_b = parent_and_quarter(second_group, second_subject)
    if parent_a != parent_b:
        return False
    return quarter_a is not None and quarter_b is not None and quarter_a != quarter_b
