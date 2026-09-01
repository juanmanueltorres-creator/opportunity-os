from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.gmail_read.models import GmailMessageEnvelope

MAX_MESSAGE_TEXT_BYTES = 256 * 1024


class StrictGmailContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GmailContentEnvelope(StrictGmailContentModel):
    message: GmailMessageEnvelope
    current_message_text: str = Field(min_length=1)


class GmailContentError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
