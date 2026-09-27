"""Emmagatzematge de propostes en memòria amb recuperació automàtica.

`proposal_store` és un diccionari en memòria compartit pels casos d'ús
(generar, acceptar, moure, assistent...). Com que no es persisteix sencer —
només es desa la *proposta pendent* dins `working_timetable.json`—, després de
reiniciar el backend (o d'un `uvicorn --reload` per qualsevol canvi de codi)
qualsevol id de proposta que la interfície encara tingui obert deixava de
trobar-se i totes aquelles accions responien `proposal_not_found`.

`ProposalStore` manté el comportament de diccionari però, quan se li demana un
id que no té, intenta reconstruir-lo de la proposta pendent desada al
snapshot. Així la interfície no queda trencada per un reinici del backend.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from backend.scheduler_engine.models import Activity, Conflict, ScheduleProposal
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.models import Activity, Conflict, ScheduleProposal


def proposal_from_snapshot_payload(payload: Optional[Dict[str, Any]]) -> Optional[ScheduleProposal]:
    """Construeix la `ScheduleProposal` a partir del payload desat al snapshot
    de l'horari (`current_proposal`). Retorna None si el payload no és
    aprofitable, en lloc de fer fallar el que l'estigui consultant."""
    if not payload or not payload.get("id"):
        return None

    try:
        return ScheduleProposal(
            id=payload["id"],
            activities=[Activity(**activity) for activity in payload.get("activities", [])],
            score=payload.get("score", 0.0),
            conflicts=[Conflict(**conflict) for conflict in payload.get("conflicts", [])],
            warnings=list(payload.get("warnings", [])),
            metadata=dict(payload.get("metadata", {})),
        )
    except (TypeError, ValueError):
        return None


class ProposalStore(dict):
    """Diccionari de propostes que recupera del snapshot la proposta pendent
    quan se li demana un id que no té en memòria."""

    def __init__(self, working_timetable_repo: Any = None) -> None:
        super().__init__()
        self._working_timetable_repo = working_timetable_repo

    def _hydrate(self, proposal_id: Any) -> Optional[ScheduleProposal]:
        repo = self._working_timetable_repo
        if repo is None or not isinstance(proposal_id, str) or not proposal_id:
            return None

        try:
            snapshot = repo.load_snapshot()
        except Exception:  # pragma: no cover - snapshot il·legible o absent
            return None

        payload = getattr(snapshot, "current_proposal", None)
        if not payload or payload.get("id") != proposal_id:
            return None

        proposal = proposal_from_snapshot_payload(payload)
        if proposal is None:
            return None

        dict.__setitem__(self, proposal_id, proposal)
        return proposal

    def get(self, proposal_id, default=None):
        proposal = dict.get(self, proposal_id)
        if proposal is not None:
            return proposal
        return self._hydrate(proposal_id) or default

    def __contains__(self, proposal_id) -> bool:
        return dict.__contains__(self, proposal_id) or self._hydrate(proposal_id) is not None

    def __missing__(self, proposal_id):
        """Permet `store[proposal_id]` (undo/redo fan servir aquesta via)."""
        proposal = self._hydrate(proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        return proposal
