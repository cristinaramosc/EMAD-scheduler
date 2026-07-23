from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if __package__ and __package__.startswith("backend"):
    from backend.dependencies import get_assistant_use_cases
else:  # pragma: no cover
    from dependencies import get_assistant_use_cases

router = APIRouter(prefix="/assistant", tags=["Assistant"])


class AssistantChatDTO(BaseModel):
    proposal_id: str
    message: str


@router.post("/chat")
def assistant_chat(payload: AssistantChatDTO):
    use_cases = get_assistant_use_cases()
    try:
        return use_cases.ask(payload.proposal_id, payload.message)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal_not_found")
