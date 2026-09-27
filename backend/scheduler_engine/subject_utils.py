"""Utilitats compartides per classificar assignatures pel seu nom.

El cas de referència és la **Tutoria** (l'hora de tutoria del tutor/a, també
la que dedica a les famílies): ocupa la franja del professor que la fa, però
**no és lectiva per als alumnes** — no ha d'ocupar la graella del grup ni
comptar com a dia lectiu, i als fulls d'horari surt com a informació.

Aquesta regla vivia duplicada (i amb coincidència exacta de text) a
`constraints/group_conflict.py`, `constraints/group_max_days.py` i
`services/schedule_exporter.py`; per això noms reals com `PFI Tutoria` o
`Tutoria famílies` no s'hi reconeixien. Ara hi ha una única implementació
aquí, igual que `quarter_utils.py` concentra la regla dels quadrimestres.
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
