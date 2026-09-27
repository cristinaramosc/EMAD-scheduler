"""Configuració comuna dels tests del backend.

Hi ha tests que fan servir `get_live_schedule_use_cases()` o
`get_scheduler_use_cases()` sense redirigir `EMAD_WORKING_TIMETABLE_FILE`;
com que el repositori per defecte és `backend/data/working_timetable.json`,
aquests tests escrivien l'horari a sobre de les **dades reals de treball** i
les deixaven reduïdes a l'última activitat carregada pel test.

Aquesta fixture (autouse) desvia sempre aquell fitxer cap a un directori
temporal, de manera que cap test pugui modificar les dades del projecte.
Els tests que volen provar la persistència de debò (`test_working_timetable_
persistence.py`) ja fixen el seu propi valor amb `monkeypatch.setenv`, que té
precedència sobre aquesta fixture.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_working_timetable_file(tmp_path, monkeypatch):
    """Cap test ha d'escriure al `backend/data/working_timetable.json` real."""
    monkeypatch.setenv("EMAD_WORKING_TIMETABLE_FILE", str(tmp_path / "working_timetable.json"))
