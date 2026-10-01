"""Utilitats compartides per classificar assignatures pel seu nom.

La Tutoria no és lectiva per defecte, excepte la tutoria del grup PFI, que
forma part de l'horari de classe. Totes ocupen la franja del professor.

Aquesta regla vivia duplicada (i amb coincidència exacta de text) a
`constraints/group_conflict.py`, `constraints/group_max_days.py` i
`services/schedule_exporter.py`; `is_non_lective_tutoria` aplica la regla
tenint en compte el grup. Així `PFI Tutoria` és lectiva per a PFI, però no
per a un altre grup. `quarter_utils.py` concentra la regla dels quadrimestres.
"""

from __future__ import annotations

import re
from typing import List, Optional

#: Paraules que identifiquen una hora de tutoria dins el nom de l'assignatura.
_TUTORIA_TOKENS = {"tutoria", "tutories"}


def _subject_tokens(subject: Optional[str]) -> List[str]:
    """Separa el nom de l'assignatura en paraules (sense accents ni signes),
    per poder comparar-hi paraules senceres i no trossos de text."""
    return [token for token in re.split(r"[^\w]+", str(subject or "").casefold()) if token]


def is_tutoria_subject(subject: Optional[str]) -> bool:
    """Retorna True si el nom de l'assignatura és (o conté com a paraula)
    `Tutoria`/`Tutories`: `Tutoria`, `PFI Tutoria`, `Tutoria famílies`,
    `Tutoria de famílies`, `Tutoria 1r COM`, etc.

    Es compara per paraules senceres per no confondre cap codi ni cap nom que
    només contingui la cadena de text per casualitat.
    """
    return any(token in _TUTORIA_TOKENS for token in _subject_tokens(subject))


def is_non_lective_tutoria(subject: Optional[str], group: Optional[str]) -> bool:
    """PFI Tutoria is lective for PFI; other tutoring activities are not."""
    if not is_tutoria_subject(subject):
        return False
    return "pfi" not in _subject_tokens(group)
