from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional

try:
    from backend.application.assistant_tools import AssistantToolbox, PendingAction
    from backend.scheduler_engine.models import ScheduleProposal
except ModuleNotFoundError:  # pragma: no cover
    from application.assistant_tools import AssistantToolbox, PendingAction
    from scheduler_engine.models import ScheduleProposal


DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOOL_ROUNDS = 8
MAX_PENDING_ACTIONS = 100
MAX_TOOL_RESULT_CHARS = 12000


SYSTEM_PROMPT = """Ets l'assistent de l'EMAD-Scheduler: ajudes la coordinació i el professorat a entendre, \
revisar i millorar els horaris del centre. Treballes com una persona experta amb l'horari davant: consultes \
les dades amb les teves eines, raones i proposes canvis concrets.

COM TREBALLES
- Abans de respondre sobre dades concretes (qui fa classe, a quina hora, hores d'un professor, forats, \
conflictes, restriccions), CONSULTA-HO amb les eines. No t'ho inventis ni ho donis de memòria.
- Per moure una activitat: troba l'id amb get_schedule, comprova-la amb check_move o find_free_slots i, si \
té sentit, registra-la amb propose_move explicant el motiu.
- NO pots aplicar cap canvi. propose_move i propose_toggle_break només deixen una proposta pendent: la \
persona veurà un botó "Aplica" i decidirà. No diguis mai que alguna cosa "s'ha canviat"; digues que la \
deixes proposada.
- Si una eina diu que un moviment no és vàlid, explica el motiu real (conflicte o franja no disponible) i \
prova una altra opció abans de rendir-te.
- Si les dades no permeten una resposta concloent, digues-ho. Mai presentis hipòtesis com fets.
- Si et demanen un objectiu obert ("com puc millorar l'horari?"), comença per les dades (get_overview, \
get_problems, get_person_summary) i proposa un pla ordenat, començant pel més rellevant.
- Si la persona rebutja una recomanació, respecta-ho; pots oferir alternatives.

CRITERIS DEL CENTRE (tenen prioritat quan valores un horari o un canvi)
- La disponibilitat dels professors és una restricció dura: no es pot canviar.
- Cada grup ha de tenir com a màxim una franja buida al dia, descomptant fins a 1 hora de dinar (12:00-16:00).
- Un 1Q o un 2Q que queda sol (sense parella 2Q/1Q al seu grup) ha d'anar a primera o a última hora del \
dia del grup. Un 1Q i un 2Q del mateix professor poden compartir franja, també entre grups diferents.
- Els descansos són un forat horitzontal que desplaça les classes; mai poden coincidir amb una classe.
- Es valora que les hores d'un grup estiguin repartides de manera equilibrada entre els dies, i que els \
professors tinguin el mínim de forats.
- Les activitats marcades [FIX] no es poden moure.

ESTIL
- Català, clar i directe, sense argot tècnic innecessari. Respostes breus per a preguntes concretes; més \
àmplies només quan calgui explicar un raonament.
- Quan compares alternatives, sigues concret i neutral: avantatges i inconvenients de cadascuna, \
referint-te a les restriccions reals de professors i grups.
- Les hores d'inici/final i els dies que dius han de coincidir amb el que han retornat les eines."""


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


def _involved_names(proposal: ScheduleProposal) -> Dict[str, set]:
    """Extreu els noms de professors i grups implicats en conflictes o
    activitats sense col·locar, per poder-hi acotar les restriccions."""
    teachers: set = set()
    groups: set = set()

    for conflict in proposal.conflicts or []:
        if getattr(conflict, "teacher", None):
            teachers.add(conflict.teacher)

    for warning in proposal.warnings or []:
        if not isinstance(warning, dict):
            continue
        if warning.get("teacher"):
            teachers.add(warning["teacher"])
        if warning.get("group"):
            groups.add(warning["group"])

    return {"teachers": teachers, "groups": groups}


def _format_restrictions(
    academic_data_repo: Optional[Any], teachers: set, groups: set
) -> str:
    if academic_data_repo is None or (not teachers and not groups):
        return "No hi ha restriccions conegudes rellevants per aquesta proposta."

    lines: List[str] = []

    try:
        teacher_restrictions = academic_data_repo.list_teacher_restrictions()
    except Exception:  # pragma: no cover - defensiu, no ha de trencar el xat
        teacher_restrictions = []
    for record in teacher_restrictions:
        if record.get("teacher") not in teachers:
            continue
        slots = record.get("unavailable_slots") or []
        if slots:
            lines.append(f"- Professor {record['teacher']}: no disponible a {', '.join(slots)}")

    try:
        group_restrictions = academic_data_repo.list_group_restrictions()
    except Exception:  # pragma: no cover
        group_restrictions = []
    for record in group_restrictions:
        if record.get("group") not in groups:
            continue
        unavailable = record.get("unavailable_slots") or []
        fixed = record.get("fixed_slots") or []
        if unavailable:
            lines.append(f"- Grup {record['group']}: no disponible a {', '.join(unavailable)}")
        if fixed:
            lines.append(f"- Grup {record['group']}: activitats fixes a {', '.join(fixed)}")

    if not lines:
        return "No hi ha restriccions conegudes rellevants per aquesta proposta."
    return "\n".join(lines)


def build_context_summary(
    proposal: ScheduleProposal, academic_data_repo: Optional[Any] = None
) -> str:
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
    involved = _involved_names(proposal)

    return (
        f"Proposta: {proposal.id}\n"
        f"Puntuació: {proposal.score}\n"
        f"Activitats col·locades: {len(proposal.activities or [])}\n"
        f"Activitats sense col·locar: {len(warnings)}\n\n"
        f"CONFLICTES REALS:\n{_format_conflicts(conflicts)}\n\n"
        f"ACTIVITATS SENSE FRANJA:\n{_format_warnings(warnings)}\n\n"
        f"RESTRICCIONS DE PROFESSORS I GRUPS IMPLICATS:\n"
        f"{_format_restrictions(academic_data_repo, involved['teachers'], involved['groups'])}"
    )


def _activity_to_dict(activity: Any) -> Dict[str, Any]:
    getter = (lambda key: activity.get(key)) if isinstance(activity, dict) else (lambda key: getattr(activity, key, None))
    return {
        "id": getter("id"),
        "teacher": getter("teacher") or "",
        "subject": getter("subject") or "",
        "group": getter("group") or "",
        "room": getter("room") or "",
        "day": getter("day") or "",
        "start": getter("start") or "",
        "duration": int(getter("duration") or 0),
        "fixed": bool(getter("fixed")),
    }


def _conflict_to_dict(conflict: Any) -> Dict[str, Any]:
    if isinstance(conflict, dict):
        return {"type": conflict.get("type", "conflicte"), "message": conflict.get("message", "")}
    return {"type": getattr(conflict, "type", "conflicte"), "message": getattr(conflict, "message", "")}


class AssistantUseCases:
    def __init__(
        self,
        proposal_store: Dict[str, ScheduleProposal],
        model: Optional[str] = None,
        academic_data_repo: Optional[Any] = None,
        live_schedule_use_cases: Optional[Any] = None,
        scheduler_use_cases: Optional[Any] = None,
        client_factory: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._proposal_store = proposal_store
        self._model = model or os.environ.get("EMAD_ASSISTANT_MODEL", DEFAULT_MODEL)
        self._academic_data_repo = academic_data_repo
        self._live = live_schedule_use_cases
        self._scheduler = scheduler_use_cases
        self._client_factory = client_factory
        self._pending_actions: Dict[str, PendingAction] = {}
        self._lock = threading.Lock()

    # ----------------------------------------------------------------- estat
    def status(self) -> Dict[str, Any]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {
                "configured": False,
                "error": "missing_api_key",
                "detail": "Cal definir la variable d'entorn ANTHROPIC_API_KEY al backend.",
                "model": self._model,
            }
        if self._client_factory is None:
            try:
                import anthropic  # noqa: F401
            except ModuleNotFoundError:
                return {
                    "configured": False,
                    "error": "missing_dependency",
                    "detail": "Cal instal·lar el paquet 'anthropic' (pip install anthropic).",
                    "model": self._model,
                }
        return {"configured": True, "model": self._model}

    # ----------------------------------------------------------- accions
    def _register_action(self, action: PendingAction) -> None:
        with self._lock:
            if len(self._pending_actions) >= MAX_PENDING_ACTIONS:
                oldest = next(iter(self._pending_actions))
                self._pending_actions.pop(oldest, None)
            self._pending_actions[action.id] = action

    def discard_action(self, action_id: str) -> Dict[str, Any]:
        with self._lock:
            action = self._pending_actions.pop(action_id, None)
        if action is None:
            raise LookupError("action_not_found")
        return {"ok": True, "discarded": action.id}

    def apply_action(self, action_id: str) -> Dict[str, Any]:
        """Executa una acció proposada per l'assistent. És l'ÚNIC camí pel qual
        l'assistent pot canviar l'horari, i només es crida quan la persona
        usuària prem 'Aplica'."""
        with self._lock:
            action = self._pending_actions.pop(action_id, None)
        if action is None:
            raise LookupError("action_not_found")

        if action.kind == "move":
            payload = action.payload
            if action.source == "proposal" and action.proposal_id and self._scheduler is not None:
                result = self._scheduler.move_proposal_activity(
                    action.proposal_id, payload["activity_id"], payload["day"], payload["start"]
                )
            elif self._live is not None:
                result = self._live.move(payload["activity_id"], payload["day"], payload["start"])
            else:
                return {"ok": False, "error": "unavailable", "detail": "No es pot aplicar: l'horari no està disponible."}
        elif action.kind == "toggle_break":
            if self._live is None:
                return {"ok": False, "error": "unavailable", "detail": "No es pot aplicar: l'horari no està disponible."}
            result = self._live.toggle_group_break(action.payload["group"], action.payload["day"])
        else:  # pragma: no cover
            return {"ok": False, "error": "unknown_action"}

        ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
        response: Dict[str, Any] = {"ok": ok, "description": action.description}
        if not ok:
            response["error"] = (result or {}).get("error", "action_failed")
            response["detail"] = (result or {}).get("detail") or (result or {}).get("message") or ""
            if (result or {}).get("conflicts"):
                response["conflicts"] = result["conflicts"]
        return response

    # ------------------------------------------------------------- context
    def _load_schedule(self, proposal: Optional[ScheduleProposal], proposal_id: Optional[str]):
        """(source, activities, conflicts, unplaced, resum) de l'horari que
        la persona veu ara mateix, o None si no n'hi ha cap."""
        if proposal is not None:
            activities = [_activity_to_dict(item) for item in (proposal.activities or [])]
            conflicts = [_conflict_to_dict(item) for item in (proposal.conflicts or [])]
            unplaced = [item for item in (proposal.warnings or []) if isinstance(item, dict)]
            summary = build_context_summary(proposal, self._academic_data_repo)
            return "proposal", activities, conflicts, unplaced, summary

        if self._live is None:
            return None
        state = self._live.state()
        activities = [_activity_to_dict(item) for item in (state.get("activities") or [])]
        if not activities:
            return None
        conflicts = [_conflict_to_dict(item) for item in (state.get("conflicts") or [])]
        unplaced = [item for item in (state.get("unscheduled_activities") or []) if isinstance(item, dict)]
        summary = (
            "Horari actiu (acceptat).\n"
            f"Activitats col·locades: {len(activities)}\n"
            f"Activitats sense col·locar: {len(unplaced)}\n\n"
            f"CONFLICTES REALS:\n{_format_conflicts(conflicts)}\n\n"
            f"ACTIVITATS SENSE FRANJA:\n{_format_warnings(unplaced)}"
        )
        return "live", activities, conflicts, unplaced, summary

    def _make_client(self, api_key: str):
        if self._client_factory is not None:
            return self._client_factory(api_key)
        import anthropic

        return anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------ ask
    def ask(
        self,
        proposal_id: Optional[str],
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        proposal = None
        if proposal_id:
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

        if self._client_factory is None:
            try:
                import anthropic  # noqa: F401
            except ModuleNotFoundError:
                return {
                    "ok": False,
                    "error": "missing_dependency",
                    "detail": "Cal instal·lar el paquet 'anthropic' (pip install anthropic).",
                }

        loaded = self._load_schedule(proposal, proposal_id)
        if loaded is None:
            return {
                "ok": False,
                "error": "no_schedule",
                "detail": "Encara no hi ha cap horari: genera'n un o acepta una proposta.",
            }
        source, activities, conflicts, unplaced, context_summary = loaded

        turn_actions: List[PendingAction] = []

        def register(action: PendingAction) -> None:
            turn_actions.append(action)
            self._register_action(action)

        toolbox = AssistantToolbox(
            source=source,
            proposal_id=proposal_id if source == "proposal" else None,
            activities=activities,
            conflicts=conflicts,
            unplaced=unplaced,
            academic_data_repo=self._academic_data_repo,
            register_action=register,
            new_action_id=lambda: uuid.uuid4().hex[:12],
        )

        # Torns anteriors de la conversa (sense recontext, per no repetir
        # el resum a cada torn): el context fresc només s'adjunta a la
        # pregunta actual, ja que l'estat de l'horari pot haver canviat.
        conversation_messages: List[Dict[str, Any]] = []
        for turn in history or []:
            role = turn.get("role")
            text = turn.get("text") or turn.get("content")
            if role not in ("user", "assistant") or not text:
                continue
            conversation_messages.append({"role": role, "content": text})

        conversation_messages.append(
            {
                "role": "user",
                "content": (
                    f"Context de l'horari actual:\n\n{context_summary}\n\n"
                    f"Pregunta de la persona usuària: {message}"
                ),
            }
        )

        client = self._make_client(api_key)
        reply_text = ""
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = client.messages.create(
                    model=self._model,
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    tools=toolbox.definitions(),
                    messages=conversation_messages,
                )
                blocks = list(response.content or [])
                reply_text = "".join(
                    block.text for block in blocks if getattr(block, "type", None) == "text"
                )
                tool_calls = [block for block in blocks if getattr(block, "type", None) == "tool_use"]
                if getattr(response, "stop_reason", None) != "tool_use" or not tool_calls:
                    break

                conversation_messages.append(
                    {"role": "assistant", "content": [self._block_to_param(block) for block in blocks]}
                )
                results = []
                for call in tool_calls:
                    output = toolbox.call(call.name, call.input if isinstance(call.input, dict) else {})
                    text_output = json.dumps(output, ensure_ascii=False)
                    if len(text_output) > MAX_TOOL_RESULT_CHARS:
                        text_output = text_output[:MAX_TOOL_RESULT_CHARS] + "… [resultat truncat]"
                    results.append({"type": "tool_result", "tool_use_id": call.id, "content": text_output})
                conversation_messages.append({"role": "user", "content": results})
            else:
                reply_text = (
                    reply_text
                    or "No he pogut acabar l'anàlisi (massa passos). Prova de concretar més la pregunta."
                )
        except Exception as exc:  # pragma: no cover - depends on live network/API
            return {"ok": False, "error": "api_call_failed", "detail": str(exc)}

        if not reply_text.strip():
            reply_text = "He deixat les accions proposades a sota." if turn_actions else "No tinc cap resposta."

        return {
            "ok": True,
            "reply": reply_text,
            "actions": [action.public() for action in turn_actions],
        }

    @staticmethod
    def _block_to_param(block: Any) -> Dict[str, Any]:
        if getattr(block, "type", None) == "tool_use":
            return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
        return {"type": "text", "text": getattr(block, "text", "")}
