from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if __package__ and __package__.startswith("backend"):
    from backend.dependencies import get_assistant_use_cases
else:  # pragma: no cover
    from dependencies import get_assistant_use_cases

router = APIRouter(prefix="/assistant", tags=["Assistant"])


class AssistantHistoryTurnDTO(BaseModel):
    role: str
    text: str


class AssistantChatDTO(BaseModel):
    proposal_id: Optional[str] = None
    message: str
    history: Optional[List[AssistantHistoryTurnDTO]] = None


@router.post("/chat")
def assistant_chat(payload: AssistantChatDTO):
    use_cases = get_assistant_use_cases()
    history = [turn.model_dump() for turn in (payload.history or [])]
    try:
        return use_cases.ask(payload.proposal_id, payload.message, history=history)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal_not_found")


@router.get("/status")
def assistant_status():
    return get_assistant_use_cases().status()


@router.post("/actions/{action_id}/apply")
def assistant_apply_action(action_id: str):
    """Aplica una acció que l'assistent havia proposat. Només la persona
    usuària hi arriba (botó 'Aplica'): l'assistent no pot executar-la sola."""
    try:
        return get_assistant_use_cases().apply_action(action_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="action_not_found")


@router.post("/actions/{action_id}/discard")
def assistant_discard_action(action_id: str):
    try:
        return get_assistant_use_cases().discard_action(action_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="action_not_found")
