"""Assistent amb un servei gratuït compatible amb OpenAI (Groq): el bucle
d'eines i la configuració, sense xarxa (el servei es simula)."""

import json

import pytest

from backend.application.assistant_use_cases import GROQ_BASE_URL, GROQ_DEFAULT_MODEL, AssistantUseCases
from backend.tests.test_assistant_agent import _live, _positions


@pytest.fixture(autouse=True)
def _only_groq(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "EMAD_ASSISTANT_PROVIDER", "EMAD_ASSISTANT_BASE_URL",
                 "EMAD_ASSISTANT_API_KEY", "EMAD_ASSISTANT_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")


def _reply(text="", tool_calls=None):
    message = {"role": "assistant", "content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def _call(name, arguments, call_id="call_1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def _assistant(script, calls):
    def fake_post(url, headers, payload):
        calls.append({"url": url, "headers": headers, "payload": json.loads(json.dumps(payload))})
        return script.pop(0)

    live = _live()
    return AssistantUseCases(
        proposal_store={},
        academic_data_repo=live._academic_data_repo,
        live_schedule_use_cases=live,
        http_post=fake_post,
    ), live


def test_groq_is_configured_with_only_a_groq_key_and_uses_its_default_model():
    assistant, _ = _assistant([], [])
    assert assistant.status() == {"configured": True, "model": GROQ_DEFAULT_MODEL}


def test_status_asks_for_a_key_when_none_is_set(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    assistant, _ = _assistant([], [])
    status = assistant.status()
    assert status["configured"] is False and status["error"] == "missing_api_key"
    assert "GROQ_API_KEY" in status["detail"]


def test_tool_results_are_fed_back_in_openai_format():
    calls = []
    assistant, _ = _assistant(
        [_reply(tool_calls=[_call("get_schedule", {"group": "1A"})]), _reply("1A té Mat i Hist dilluns.")],
        calls,
    )

    result = assistant.ask(None, "Què fa 1A?")

    assert result == {"ok": True, "reply": "1A té Mat i Hist dilluns.", "actions": []}
    assert len(calls) == 2
    assert calls[0]["url"] == f"{GROQ_BASE_URL}/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer gsk_test"
    assert calls[0]["payload"]["model"] == GROQ_DEFAULT_MODEL
    assert calls[0]["payload"]["messages"][0]["role"] == "system"
    assert calls[0]["payload"]["tools"][0]["type"] == "function"
    follow_up = calls[1]["payload"]["messages"]
    assert follow_up[-2]["role"] == "assistant" and follow_up[-2]["tool_calls"]
    assert follow_up[-1]["role"] == "tool" and follow_up[-1]["tool_call_id"] == "call_1"
    assert "Mat" in follow_up[-1]["content"] and "Dib" not in follow_up[-1]["content"]


def test_a_proposed_move_is_not_applied_until_the_person_confirms():
    assistant, live = _assistant(
        [
            _reply(tool_calls=[_call("propose_move", {"activity_id": 2, "day": "Dimarts", "start": "10:00", "reason": "equilibrar"})]),
            _reply("T'ho deixo proposat."),
        ],
        [],
    )
    before = _positions(live)

    result = assistant.ask(None, "Mou Hist a dimarts")

    assert len(result["actions"]) == 1
    assert _positions(live) == before  # encara NO s'ha aplicat
    assistant.apply_action(result["actions"][0]["id"])
    assert _positions(live)[2] == ("Dimarts", "10:00")


def test_a_service_error_is_reported_instead_of_crashing():
    live = _live()

    def failing_post(url, headers, payload):
        raise RuntimeError("S'ha arribat al límit gratuït del servei. Espera una estona i torna-ho a provar.")

    assistant = AssistantUseCases(
        proposal_store={}, academic_data_repo=live._academic_data_repo,
        live_schedule_use_cases=live, http_post=failing_post,
    )

    result = assistant.ask(None, "Hola")

    assert result["ok"] is False and result["error"] == "api_call_failed"
    assert "límit gratuït" in result["detail"]


def test_claude_stays_the_default_when_both_keys_exist(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assistant, _ = _assistant([], [])
    assert assistant.status()["model"] == "claude-sonnet-5-5"


def test_https_uses_a_context_that_does_not_depend_on_the_python_certificates():
    from backend.application.assistant_use_cases import _ssl_context

    context = _ssl_context()
    assert context is not None and context.verify_mode.name == "CERT_REQUIRED"
