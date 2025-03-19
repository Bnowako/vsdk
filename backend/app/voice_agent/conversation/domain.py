from typing import Literal, Union

from pydantic import BaseModel

from app.voice_agent.domain import RespondToHumanResult


class StopSpeakingEvent(BaseModel):
    type: Literal["stop_speaking"] = "stop_speaking"


class MediaEvent(BaseModel):
    type: Literal["media"] = "media"
    audio: bytes
    sid: str


class MarkEvent(BaseModel):
    type: Literal["mark"] = "mark"
    mark_id: str
    sid: str


class ResultEvent(BaseModel):
    type: Literal["result"] = "result"
    result: RespondToHumanResult


class RestreamAudioEvent(BaseModel):
    type: Literal["start_restream"] = "start_restream"


class StartRespondingEvent(BaseModel):
    type: Literal["start_responding"] = "start_responding"


# Union type for all possible events
ConversationEvent = Union[
    StopSpeakingEvent,
    MediaEvent,
    MarkEvent,
    ResultEvent,
    RestreamAudioEvent,
    StartRespondingEvent,
]
