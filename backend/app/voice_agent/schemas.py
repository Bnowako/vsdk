from pydantic import BaseModel
from typing import Literal, Union


class StartData(BaseModel):
    streamSid: str
    accountSid: str
    callSid: str


class StartEvent(BaseModel):
    event: Literal["start"] = "start"
    start: StartData


class MediaData(BaseModel):
    payload: str


class MediaEvent(BaseModel):
    event: Literal["media"] = "media"
    media: MediaData


class MarkData(BaseModel):
    name: str


class MarkEvent(BaseModel):
    event: Literal["mark"] = "mark"
    mark: MarkData


class ClearEvent(BaseModel):
    event: Literal["clear"] = "clear"


class ClosedEvent(BaseModel):
    event: Literal["closed"] = "closed"


class CycleResult(BaseModel):
    stt_duration: float
    llm_duration: float
    tts_duration: float
    total_duration: float
    first_chunk_time: float
    transcript: str
    response: str


class ResultEvent(BaseModel):
    event: Literal["result"] = "result"
    result: CycleResult


EventType = Union[
    StartEvent,
    MediaEvent,
    MarkEvent,
    ClearEvent,
    ClosedEvent,
]
