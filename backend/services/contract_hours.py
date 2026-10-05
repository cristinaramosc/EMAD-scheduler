"""Hores de contracte d'un professor segons el seu percentatge de jornada.

Taula de referència (PERCENTATGES_EMAD.xlsx): sobre una jornada completa
(100 %) cada setmana hi ha 20 h lectives, 7,5 h de centre i 7,5 h de
preparació (35 h en total); cada hora lectiva és un 5 % de la jornada. Les
hores lectives inclouen les coordinacions i les tutories; les de centre
inclouen la reunió de claustre i la coordinació fixa de dimecres.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

FULL_TIME_LECTIVE_HOURS = 20.0
FULL_TIME_CENTRE_HOURS = 7.5
FULL_TIME_PREPARATION_HOURS = 7.5


def parse_dedication_pct(value: Any) -> Optional[float]:
    """Converteix el percentatge de jornada a un nombre de 0 a 100.

    Accepta `100`, `"52,5"`, `"52.5 %"` i també fraccions (`0.525` → 52,5),
    com les que fa servir el full de càlcul. Retorna None si és buit o no és
    vàlid, i no admet valors negatius ni superiors al 100 %.
    """
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", ".").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number <= 0:
        return None
    if number <= 1.0:
        number *= 100
    if number > 100:
        return None
    return round(number, 3)


def contract_hours(pct: Any) -> Optional[Dict[str, float]]:
    """Hores setmanals de contracte (lectives, centre, preparació i total)
    per a un percentatge de jornada, o None si no n'hi ha cap."""
    percent = parse_dedication_pct(pct)
    if percent is None:
        return None
    fraction = percent / 100
    lective = round(fraction * FULL_TIME_LECTIVE_HOURS, 2)
    centre = round(fraction * FULL_TIME_CENTRE_HOURS, 2)
    preparation = round(fraction * FULL_TIME_PREPARATION_HOURS, 2)
    return {
        "pct": percent,
        "lective": lective,
        "centre": centre,
        "preparation": preparation,
        "total": round(lective + centre + preparation, 2),
    }
