from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

try:
    from backend.scheduler_engine.models import ScheduleProposal
except ModuleNotFoundError:  # pragma: no cover
    from scheduler_engine.models import ScheduleProposal


# System prompt destil·lat de docs/PROMPTS/06-assistent-resolucio.md.
# Es manté aquí com a text (no es llegeix el .md en temps d'execució) perquè
# sigui explícit, versionat i no dependent de la ubicació del fitxer.
SYSTEM_PROMPT = """Ets l'assistent de resolució d'horaris de l'EMAD-Scheduler.

ROL
Ajudes professorat i coordinació a entendre i millorar un horari escolar generat automàticament.
No ets el motor de generació: no col·loques ni mous res tu mateix.

PRINCIPIS
- Explica sempre el motiu real d'una incidència o conflicte, no un resum genèric.
- Compara alternatives de manera neutral: presenta avantatges i inconvenients de cadascuna, sense imposar una opció.
- Si les dades disponibles no permeten una resposta concloent, digues-ho explícitament ("Amb les dades disponibles no es pot determinar...").
- Mai inventis dades que no estiguin al context proporcionat. Si no ho saps, digues-ho.
- No amaguis inconvenients d'una opció per fer-la semblar més atractiva.
- No presentis hipòtesis com si fossin fets.

LLENGUATGE
- Català, clar i directe, sense argot tècnic innecessari.
- Manté un estil consistent: ni excessivament tècnic ni informal.
- Respostes breus per preguntes concretes; més àmplies quan calgui explicar un raonament complex.

LÍMITS
- NO apliques mai cap canvi a l'horari; només expliques, analitzes, compares, suggereixes i justifiques.
- Qualsevol acció que impliqui modificar l'horari requereix confirmació explícita de la persona usuària fora d'aquesta conversa (aquesta versió de l'assistent és només de consulta, no executa accions).
- Si la persona rebutja una recomanació, no insisteixis; pots oferir alternatives però respecta la decisió.
- Si et pregunten un objectiu obert ("com puc millorar aquest horari?"), comença pels problemes més rellevants i proposa un pla d'acció ordenat, no una llista aïllada d'incidències.

CONTEXT
Rebràs, en cada consulta, un resum estructurat de l'estat actual de la proposta d'horari (conflictes reals i activitats que no s'han pogut col·locar, amb els seus motius). Basa les teves respostes únicament en aquest context i en el que la persona et digui a la conversa."""


def _format_conflicts(conflicts: List[Dict[str, Any]]) -> str:
    if not conflicts:
        return "Cap conflicte detectat a la proposta actual."
    lines = []
    for conflict in conflicts:
        lines.append(f"- [{conflict.get('type', 'conflicte')}] {conflict.get('message', '')}")
    return "\n".join(lines)


def _format_warnings(warnings: List[Dict[str, Any]]) -> str:
    if not warnings:
        return "Totes les activitats s'han pogut col·locar."
    lines = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        label = f"{warning.get('subject', '')} · {warning.get('teacher', '')} · {warning.get('group', '')}"
        constraints = warning.get("constraints") or []
        reasons = "; ".join(constraints) if constraints else warning.get("reason", "")
        lines.append(f"- {label}: {reasons}")
    return "\n".join(lines)


def build_context_summary(proposal: ScheduleProposal) -> str:
    """Resum estructurat i llegible de l'estat de la proposta, per fer de
    context real a la conversa (evita que l'assistent inventi dades)."""
    conflicts = [
        {
            "type": conflict.type,
            "message": conflict.message,
        }
        for conflict in (proposal.conflicts or [])
    ]
    warnings = proposal.warnings or []

    return (
        f"Proposta: {proposal.id}\n"
        f"Puntuació: {proposal.score}\n"
        f"Activitats col·locades: {len(proposal.activities or [])}\n"
        f"Activitats sense col·locar: {len(warnings)}\n\n"
        f"CONFLICTES REALS:\n{_format_conflicts(conflicts)}\n\n"
        f"ACTIVITATS SENSE FRANJA:\n{_format_warnings(warnings)}"
    )


class AssistantUseCases:
    def __init__(self, proposal_store: Dict[str, ScheduleProposal], model: Optional[str] = None) -> None:
        self._proposal_store = proposal_store
        self._model = model or os.environ.get("EMAD_ASSISTANT_MODEL", "claude-sonnet-4-6")

    def ask(self, proposal_id: str, message: str) -> Dict[str, Any]:
        proposal = self._proposal_store.get(proposal_id)
        if proposal is None:
            raise LookupError("proposal_not_found")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return {
                "ok": False,
                "error": "missing_api_key",
                "detail": "Cal configurar la variable d'entorn ANTHROPIC_API_KEY al backend.",
            }

        try:
            import anthropic
        except ModuleNotFoundError:
            return {
                "ok": False,
                "error": "missing_dependency",
                "detail": "Cal instal·lar el paquet 'anthropic' (pip install anthropic).",
            }

        context_summary = build_context_summary(proposal)

        client = anthropic.Anthropic(api_key=api_key)
        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Context de la proposta actual:\n\n{context_summary}\n\n"
                            f"Pregunta de la persona usuària: {message}"
                        ),
                    }
                ],
            )
        except Exception as exc:  # pragma: no cover - depends on live network/API
            return {"ok": False, "error": "api_call_failed", "detail": str(exc)}

        reply_text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )

        return {"ok": True, "reply": reply_text}
