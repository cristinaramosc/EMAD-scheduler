import types

import pytest

from backend.application.assistant_use_cases import MAX_TOOL_ROUNDS, AssistantUseCases
from backend.application.live_schedule_use_cases import LiveScheduleUseCases
from backend.repositories.academic_data_repository import AcademicDataRepository
from backend.repositories.working_timetable_repository import WorkingTimetableRepository, WorkingTimetableSnapshot
from backend.scheduler_engine.engine import SchedulerEngine
from backend.scheduler_engine.models import ScheduleProposal
from backend.scheduler_engine.models.activity import Activity


class _MemoryRepo(WorkingTimetableRepository):
    def __init__(self) -> None:
        self._snapshot = WorkingTimetableSnapshot()

    def load_snapshot(self) -> WorkingTimetableSnapshot:
        return self._snapshot

    def save_snapshot(self, snapshot: WorkingTimetableSnapshot) -> None:
        self._snapshot = snapshot


ACTIVITIES = [
    {"id": 1, "teacher": "Ana", "subject": "Mat", "group": "1A", "room": "R1", "day": "Dilluns", "start": "8:00", "duration": 2},
    {"id": 2, "teacher": "Berta", "subject": "Hist", "group": "1A", "room": "R2", "day": "Dilluns", "start": "10:00", "duration": 2},
    {"id": 3, "teacher": "Ana", "subject": "Dib", "group": "2A", "room": "R1", "day": "Dilluns", "start": "12:00", "duration": 2},
]


def _live(academic_repo=None) -> LiveScheduleUseCases:
    use_cases = LiveScheduleUseCases(
        engine=SchedulerEngine(),
        working_timetable_repo=_MemoryRepo(),
        academic_data_repo=academic_repo or AcademicDataRepository(),
    )
    use_cases.load([dict(item) for item in ACTIVITIES])
    return use_cases


class _RestrictedRepo(AcademicDataRepository):
    """Ana no pot venir dimarts a les 8:00 (ni 8:30)."""

    def list_teacher_restrictions(self):
        return [{"teacher": "Ana", "unavailable_slots": ["Dimarts 8:00", "Dimarts 8:30"]}]


class _ScriptedClient:
    """Client d'Anthropic simulat: respon amb el guió donat, una resposta per crida."""

    def __init__(self, script, calls):
        self._script = list(script)
        self.messages = types.SimpleNamespace(create=self._create)
        self._calls = calls

    def _create(self, **kwargs):
        self._calls.append(kwargs)
        return self._script.pop(0) if self._script else _text("Fi")


def _text(text):
    return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=text)], stop_reason="end_turn")


def _tool(name, arguments, call_id="tu_1", text=""):
    blocks = []
    if text:
        blocks.append(types.SimpleNamespace(type="text", text=text))
    blocks.append(types.SimpleNamespace(type="tool_use", id=call_id, name=name, input=arguments))
    return types.SimpleNamespace(content=blocks, stop_reason="tool_use")


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def _assistant(script, live=None, repo=None, calls=None, **kwargs):
    calls = calls if calls is not None else []
    live = live or _live(repo)
    return (
        AssistantUseCases(
            proposal_store={},
            academic_data_repo=repo or live._academic_data_repo,
            live_schedule_use_cases=live,
            client_factory=lambda api_key: _ScriptedClient(script, calls),
            **kwargs,
        ),
        live,
        calls,
    )


def _positions(live):
    return {item["id"]: (item["day"], item["start"]) for item in live.state()["activities"]}


def test_tool_results_are_fed_back_to_the_model_and_the_final_text_is_returned():
    assistant, _, calls = _assistant(
        [_tool("get_schedule", {"group": "1A"}), _text("1A té Mat i Hist dilluns.")]
    )

    result = assistant.ask(None, "Què fa 1A?")

    assert result == {"ok": True, "reply": "1A té Mat i Hist dilluns.", "actions": []}
    assert len(calls) == 2
    assert calls[0]["tools"], "l'assistent ha de rebre les eines"
    follow_up = calls[1]["messages"]
    assert follow_up[-2]["role"] == "assistant"
    assert follow_up[-2]["content"][0]["type"] == "tool_use"
    tool_result = follow_up[-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "tu_1"
    assert "Mat" in tool_result["content"] and "Hist" in tool_result["content"]
    assert "Dib" not in tool_result["content"]  # és de 2A


def test_a_proposed_move_is_not_applied_until_the_person_confirms():
    assistant, live, _ = _assistant(
        [
            _tool("propose_move", {"activity_id": 2, "day": "Dimarts", "start": "10:00", "reason": "equilibrar"}),
            _text("T'ho deixo proposat."),
        ]
    )
    before = _positions(live)

    result = assistant.ask(None, "Mou Hist a dimarts")

    assert len(result["actions"]) == 1
    action = result["actions"][0]
    assert action["kind"] == "move" and "Dimarts 10:00" in action["description"]
    assert _positions(live) == before  # encara NO s'ha aplicat

    applied = assistant.apply_action(action["id"])

    assert applied["ok"] is True
    assert _positions(live)[2] == ("Dimarts", "10:00")
    with pytest.raises(LookupError):  # una acció només es pot aplicar una vegada
        assistant.apply_action(action["id"])


def test_discarded_actions_cannot_be_applied():
    assistant, live, _ = _assistant(
        [_tool("propose_move", {"activity_id": 2, "day": "Dimarts", "start": "10:00"}), _text("ok")]
    )
    action = assistant.ask(None, "Mou Hist")["actions"][0]

    assert assistant.discard_action(action["id"])["ok"] is True

    with pytest.raises(LookupError):
        assistant.apply_action(action["id"])
    assert _positions(live)[2] == ("Dilluns", "10:00")


def test_moves_that_create_conflicts_or_hit_unavailable_slots_are_not_proposed():
    assistant, live, _ = _assistant(
        [
            _tool("propose_move", {"activity_id": 2, "day": "Dilluns", "start": "8:00"}, "a"),
            _text("No es pot."),
        ]
    )
    result = assistant.ask(None, "Mou Hist a primera hora")
    assert result["actions"] == []  # xoca amb Mat del mateix grup

    assistant, live, calls = _assistant(
        [_tool("propose_move", {"activity_id": 1, "day": "Dimarts", "start": "8:00"}, "b"), _text("No es pot.")],
        repo=_RestrictedRepo(),
    )
    result = assistant.ask(None, "Mou Mat dimarts a les 8")
    assert result["actions"] == []
    assert "no està disponible" in calls[1]["messages"][-1]["content"][0]["content"]


def test_check_move_and_find_free_slots_respect_conflicts_and_restrictions():
    assistant, live, _ = _assistant([_text("x")], repo=_RestrictedRepo())
    toolbox = _toolbox(assistant, live)

    assert toolbox.tool_check_move(1, "Dimecres", "8:00")["ok"] is True
    assert toolbox.tool_check_move(1, "Dimarts", "8:00")["ok"] is False  # Ana no disponible
    assert toolbox.tool_check_move(3, "Dilluns", "8:00")["ok"] is False  # Ana ja fa Mat a les 8:00
    assert toolbox.tool_check_move(1, "Dimecres", "8:15")["ok"] is False  # hora invàlida
    assert toolbox.tool_check_move(99, "Dimecres", "8:00")["error"] == "activitat_no_trobada"

    free = toolbox.tool_find_free_slots(1, limit=30)
    assert free["franges_valides"] > 0
    starts = [label.split(" (")[0] for label in free["millors"]]
    assert "Dimarts 8:00" not in starts
    assert "Dilluns 10:00" not in starts  # xoca amb Hist (mateix grup)


def test_free_slots_are_ranked_by_the_gaps_they_add_and_report_the_impact():
    assistant, live, _ = _assistant([_text("x")])
    toolbox = _toolbox(assistant, live)

    ranked = toolbox.tool_find_free_slots(2, limit=30)["millors"]
    # Hist (1A) ara és a Dilluns 10:00: tornar al costat de Mat sense forat és millor que un altre dia buit.
    assert "forats grup" in ranked[0]
    first_gaps = int(ranked[0].split("forats grup ")[1].split("→")[1].split(",")[0])
    last_gaps = int(ranked[-1].split("forats grup ")[1].split("→")[1].split(",")[0])
    assert first_gaps <= last_gaps

    impact = toolbox.tool_check_move(2, "Dilluns", "14:00")["impacte"]
    assert impact["forats_grup"][1] > impact["forats_grup"][0]  # deixaria un forat al grup


def test_a_break_proposal_is_applied_only_after_confirmation():
    assistant, live, _ = _assistant(
        [_tool("propose_toggle_break", {"group": "1A", "day": "Dilluns"}), _text("Proposat.")]
    )

    result = assistant.ask(None, "Posa un descans a 1A dilluns")
    action = result["actions"][0]

    def break_days():
        records = live._academic_data_repo.list_group_restrictions()
        return next((r.get("break_days") or [] for r in records if r.get("group") == "1A"), [])

    assert break_days() == []
    assert assistant.apply_action(action["id"])["ok"] is True
    assert break_days() != []


def test_actions_on_a_pending_proposal_go_through_the_proposal_move():
    proposal = ScheduleProposal(
        id="p1",
        activities=[Activity(**{**item, "fixed": False}) for item in ACTIVITIES],
        score=1.0,
        conflicts=[],
        warnings=[],
    )
    moves = []

    class _Scheduler:
        def move_proposal_activity(self, proposal_id, activity_id, day, start):
            moves.append((proposal_id, activity_id, day, start))
            return {"ok": True}

    calls = []
    assistant = AssistantUseCases(
        proposal_store={"p1": proposal},
        scheduler_use_cases=_Scheduler(),
        client_factory=lambda api_key: _ScriptedClient(
            [_tool("propose_move", {"activity_id": 2, "day": "Dimarts", "start": "10:00"}), _text("ok")], calls
        ),
    )

    action = assistant.ask("p1", "Mou Hist")["actions"][0]
    assert moves == []
    assert assistant.apply_action(action["id"])["ok"] is True
    assert moves == [("p1", 2, "Dimarts", "10:00")]


def test_failed_apply_reports_the_reason_instead_of_pretending_success():
    class _FailingLive:
        def state(self):
            return {"activities": ACTIVITIES, "conflicts": [], "unscheduled_activities": []}

        def move(self, activity_id, day, start):
            return {"ok": False, "error": "validation_failed", "conflicts": [{"type": "x", "message": "xoc"}]}

    calls = []
    assistant = AssistantUseCases(
        proposal_store={},
        live_schedule_use_cases=_FailingLive(),
        client_factory=lambda api_key: _ScriptedClient(
            [_tool("propose_move", {"activity_id": 2, "day": "Dimarts", "start": "10:00"}), _text("ok")], calls
        ),
    )
    action = assistant.ask(None, "Mou Hist")["actions"][0]

    result = assistant.apply_action(action["id"])

    assert result["ok"] is False and result["error"] == "validation_failed"


def test_tool_loop_is_bounded_and_unknown_tools_do_not_break_the_conversation():
    script = [_tool("eina_que_no_existeix", {}, f"tu_{index}") for index in range(MAX_TOOL_ROUNDS + 3)]
    assistant, _, calls = _assistant(script)

    result = assistant.ask(None, "Hola")

    assert result["ok"] is True and result["reply"]
    assert len(calls) == MAX_TOOL_ROUNDS
    assert "eina_desconeguda" in calls[1]["messages"][-1]["content"][0]["content"]


def test_without_any_schedule_the_assistant_explains_it_cleanly():
    live = LiveScheduleUseCases(
        engine=SchedulerEngine(), working_timetable_repo=_MemoryRepo(), academic_data_repo=AcademicDataRepository()
    )
    assistant, _, calls = _assistant([_text("x")], live=live)

    result = assistant.ask(None, "Hola")

    assert result["ok"] is False and result["error"] == "no_schedule"
    assert calls == []


def test_status_reports_missing_key_and_ready_state(monkeypatch):
    assistant, _, _ = _assistant([_text("x")])
    assert assistant.status()["configured"] is True

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    status = assistant.status()
    assert status["configured"] is False and status["error"] == "missing_api_key"


def _toolbox(assistant, live):
    from backend.application.assistant_tools import AssistantToolbox

    state = live.state()
    return AssistantToolbox(
        source="live",
        proposal_id=None,
        activities=state["activities"],
        conflicts=[],
        unplaced=[],
        academic_data_repo=assistant._academic_data_repo,
        register_action=lambda action: None,
        new_action_id=lambda: "id",
    )


def test_routes_allow_chat_without_a_proposal_and_report_unknown_actions(monkeypatch):
    from fastapi import HTTPException

    from backend.routes import assistant as routes

    assistant, live, _ = _assistant(
        [_tool("propose_move", {"activity_id": 2, "day": "Dimarts", "start": "10:00"}), _text("Proposat.")]
    )
    monkeypatch.setattr(routes, "get_assistant_use_cases", lambda: assistant)

    reply = routes.assistant_chat(routes.AssistantChatDTO(message="Mou Hist a dimarts"))
    assert reply["ok"] is True and len(reply["actions"]) == 1

    assert routes.assistant_status()["configured"] is True
    assert routes.assistant_apply_action(reply["actions"][0]["id"])["ok"] is True
    assert _positions(live)[2] == ("Dimarts", "10:00")

    with pytest.raises(HTTPException) as error:
        routes.assistant_apply_action("no-existeix")
    assert error.value.status_code == 404
    with pytest.raises(HTTPException):
        routes.assistant_discard_action("no-existeix")
