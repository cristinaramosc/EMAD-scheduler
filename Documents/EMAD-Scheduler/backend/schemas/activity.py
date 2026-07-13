from pydantic import BaseModel


class ActivityUpdate(BaseModel):
    day: str
    start: str
    room: str | None = None