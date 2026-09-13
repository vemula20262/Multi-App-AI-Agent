from typing import Any, Literal

from pydantic import BaseModel, Field, StrictBool, model_validator


class TurnRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    text: str = Field(default="", max_length=8000)
    pending_interrupt_id: str | None = Field(default=None, max_length=100)
    user_permission_granted: StrictBool | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.text.strip() and self.user_permission_granted is None:
            raise ValueError("Enter a message or a permission decision.")
        return self


class TurnResponse(BaseModel):
    status: Literal["CLARIFICATION_NEEDED", "PERMISSION_REQUIRED", "COMPLETE", "ERROR"]
    interrupt_id: str | None = None
    speech_to_say: str
    action_type: str
    data: dict[str, Any] = Field(default_factory=dict)
