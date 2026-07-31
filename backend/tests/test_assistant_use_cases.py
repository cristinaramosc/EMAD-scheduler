import sys
import types

import pytest

from backend.application.assistant_use_cases import AssistantUseCases, build_context_summary
from backend.scheduler_engine.models import Conflict, ScheduleProposal


class _FakeAcademicDataRepo:
    def list_teacher_restrictions(self):
        return [
            {"teacher": "Maria Puig", "unavailable_slots": ["Dilluns 8:00"]},
            {"teacher": "Un altre", "unavailable_slots": ["Dimarts 9:00"]},
        ]

    def list_group_restrictions(self):
        return [
            {"group": "1A", "unavailable_slots": ["Divendres 15:00"], "fixed_slots": []},
        ]


def _build_proposal() -> ScheduleProposal:
    return ScheduleProposal(
        id="p1",
        activities=[],
        score=42.0,
        conflicts=[Conflict(type="teacher_conflict", message="Xoc de professor", teacher="Maria Puig")],
        warnings=[
            {"subject": "Dibuix", "teacher": "Maria Puig", "group": "1A", "constraints": ["max_consecutive_hours"]},
        ],
    )


def test_build_context_summary_includes_relevant_restrictions_only():
    proposal = _build_proposal()
    summary = build_context_summary(proposal, _FakeAcademicDataRepo())

    assert "Maria Puig" in summary
    assert "Dilluns 8:00" in summary
    assert "1A" in summary
    assert "Divendres 15:00" in summary
    # Restriccions no implicades en cap conflicte/avís no haurien d'aparèixer.
    assert "Un altre" not in summary


def test_build_context_summary_without_repo_is_safe():
    proposal = _build_proposal()
    summary = build_context_summary(proposal)
    assert "No hi ha restriccions conegudes rellevants" in summary


class _FakeMessages:
    def __init__(self, capture):
        self._capture = capture

    def create(self, **kwargs):
        self._capture.append(kwargs)
        text_block = types.SimpleNamespace(type="text", text="Resposta simulada")
        return types.SimpleNamespace(content=[text_block])


class _FakeAnthropicClient:
    def __init__(self, capture, api_key=None):
        self.messages = _FakeMessages(capture)


@pytest.fixture
def fake_anthropic(monkeypatch):
    captured_calls = []
    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = lambda api_key=None: _FakeAnthropicClient(captured_calls, api_key=api_key)
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return captured_calls


def test_ask_forwards_history_and_appends_fresh_context(fake_anthropic):
    proposal = _build_proposal()
    use_cases = AssistantUseCases(
        proposal_store={"p1": proposal},
        academic_data_repo=_FakeAcademicDataRepo(),
    )

    history = [
        {"role": "user", "text": "Quin és el conflicte principal?"},
        {"role": "assistant", "text": "El xoc de la professora Maria Puig."},
    ]

    result = use_cases.ask("p1", "I quines alternatives hi ha?", history=history)

    assert result["ok"] is True
    assert result["reply"] == "Resposta simulada"

    assert len(fake_anthropic) == 1
    messages = fake_anthropic[0]["messages"]
    # Els dos torns anteriors es reenvien tal qual.
    assert messages[0] == {"role": "user", "content": "Quin és el conflicte principal?"}
    assert messages[1] == {"role": "assistant", "content": "El xoc de la professora Maria Puig."}
    # El torn actual porta el context fresc i la pregunta nova.
    assert messages[2]["role"] == "user"
    assert "Maria Puig" in messages[2]["content"]
    assert "I quines alternatives hi ha?" in messages[2]["content"]


def test_ask_unknown_proposal_raises_lookup_error(fake_anthropic):
    use_cases = AssistantUseCases(proposal_store={})
    with pytest.raises(LookupError):
        use_cases.ask("missing", "Hola")
