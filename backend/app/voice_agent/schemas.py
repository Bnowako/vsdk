from pydantic import BaseModel
from typing import Optional, Union


# ----- Start Event -----
class StartData(BaseModel):
    streamSid: str
    accountSid: str
    callSid: str


class StartEvent(BaseModel):
    event: str = "start"
    start: StartData


# ----- Transcript Event -----
class TranscriptEvent(BaseModel):
    event: str = "transcript"
    data: str
    elapsed_time: int
    file: Optional[str] = None


# ----- Chat Response Event -----
class ChatResponseData(BaseModel):
    first_chunk_time: int
    total_time: int
    full_response: str


class ChatResponseEvent(BaseModel):
    event: str = "chat-response"
    data: ChatResponseData


# ----- TTS Time Event -----
class TTSTimeData(BaseModel):
    tts: int
    to_first_byte: int
    silence_to_first_audio_chunk: int


class TTSTimeEvent(BaseModel):
    event: str = "tts-time"
    data: TTSTimeData


# ----- Media Event -----
class MediaData(BaseModel):
    payload: str


class MediaEvent(BaseModel):
    event: str = "media"
    media: MediaData


# ----- Mark Event -----
class MarkData(BaseModel):
    name: str


class MarkEvent(BaseModel):
    event: str = "mark"
    mark: MarkData


# ----- Clear Event -----
class ClearEvent(BaseModel):
    event: str = "clear"


# ----- Closed Event (optional) -----
class ClosedEvent(BaseModel):
    event: str = "closed"


# ----- Union of All Event Types -----
EventType = Union[
    StartEvent,
    TranscriptEvent,
    ChatResponseEvent,
    TTSTimeEvent,
    MediaEvent,
    MarkEvent,
    ClearEvent,
    ClosedEvent,
]
