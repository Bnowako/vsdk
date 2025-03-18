from typing import Literal, Union

from pydantic import BaseModel

from vsdk.domain import RespondToHumanResult


class StartData(BaseModel):
    streamSid: str
    accountSid: str
    callSid: str


class TwilioStartEvent(BaseModel):
    event: Literal["start"] = "start"
    start: StartData


class MediaData(BaseModel):
    payload: str


class TwilioMediaEvent(BaseModel):
    event: Literal["media"] = "media"
    media: MediaData


class MarkData(BaseModel):
    name: str


class TwilioMarkEvent(BaseModel):
    event: Literal["mark"] = "mark"
    mark: MarkData


class ClearEventWS(BaseModel):
    event: Literal["clear"] = "clear"


class TwilioClosedEvent(BaseModel):
    event: Literal["closed"] = "closed"


class CustomResultEvent(BaseModel):
    event: Literal["result"] = "result"
    result: RespondToHumanResult


TwilioEventType = Union[
    TwilioStartEvent,
    TwilioMediaEvent,
    TwilioMarkEvent,
    ClearEventWS,
    TwilioClosedEvent,
]
