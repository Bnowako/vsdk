from typing import Literal, Union

from pydantic import BaseModel


class StartData(BaseModel):
    streamSid: str
    accountSid: str
    callSid: str


class StartEventWS(BaseModel):
    event: Literal["start"] = "start"
    start: StartData


class MediaData(BaseModel):
    payload: str


class MediaEventWS(BaseModel):
    event: Literal["media"] = "media"
    media: MediaData


class MarkData(BaseModel):
    name: str


class MarkEventWS(BaseModel):
    event: Literal["mark"] = "mark"
    mark: MarkData


class ClearEventWS(BaseModel):
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


class ResultEventWS(BaseModel):
    event: Literal["result"] = "result"
    result: CycleResult


EventType = Union[
    StartEventWS,
    MediaEventWS,
    MarkEventWS,
    ClearEventWS,
    ClosedEvent,
]
