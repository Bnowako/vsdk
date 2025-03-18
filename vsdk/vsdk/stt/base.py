from abc import ABC, abstractmethod
import base64

from pydantic import BaseModel, field_serializer


class STTResult(BaseModel):
    stt_start_time: float
    stt_end_time: float

    transcript: str
    speech_file: bytes

    @field_serializer("speech_file", when_used="json")
    def serialize_audio_in_base64(self, audio: bytes) -> str:
        return base64.b64encode(audio).decode("utf-8")

    @classmethod
    def empty(cls) -> "STTResult":
        return cls(
            stt_start_time=0,
            stt_end_time=0,
            transcript="",
            speech_file=b"",
        )


class BaseSTT(ABC):
    @abstractmethod
    async def __call__(self, pcm_audio: bytes) -> STTResult:
        pass
