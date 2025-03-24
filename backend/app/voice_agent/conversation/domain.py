import base64
from typing import Literal, Union

from pydantic import BaseModel, field_serializer

from app.voice_agent.domain import RespondToHumanResult


class StopSpeakingEvent(BaseModel):
    type: Literal["stop_speaking"] = "stop_speaking"


class MediaEvent(BaseModel):
    type: Literal["media"] = "media"
    audio: bytes
    sid: str

    @field_serializer("audio", when_used="json")
    def serialize_audio_in_base64(self, audio: bytes) -> str:
        return base64.b64encode(audio).decode("utf-8")


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


ConversationEvent = Union[
    StopSpeakingEvent,
    MediaEvent,
    MarkEvent,
    ResultEvent,
    RestreamAudioEvent,
    StartRespondingEvent,
]

ConversationEvents = Literal[
    "stop_speaking",
    "media",
    "mark",
    "result",
    "start_restream",
    "start_responding",
]
